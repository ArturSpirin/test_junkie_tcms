"""Web adapter for Reports, run in node against a live server: the org report, release readiness, the whole
product, one feature's report, the empty state, the period sent to the server, and a raw error.
Reports only read, so there is no write to read back."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_feature, ok, seed, url
from tests.execution_seed import cycle_cases, make_case, make_cycle, record
from tests.web.live import LiveServer, as_sent, body_of, run_js


@Suite(parameters=support.DATABASES)
class WebReportsAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def load(self, params):
        """The adapter's { state, data, asked } for params, signed in as the acme owner, with the shell's
        context; asked is every report path the adapter called."""
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps(params)};
            const ctx = await h.ctx(params);
            const out = await (await h.adapter("reports")).load(params, ctx);
            out.asked = h.calls.map((c) => c.path).filter((p) => p.includes("/report"));
            return out;""",
            "/app?view=reports",
        )

    def seed(self, n=2):
        """The catalog seed (PAY: Checkout › Card in release 1.0) plus n cases in one cycle of the release."""
        owner = self.live.owner
        s = seed(owner)
        cases = [make_case(owner, s["product"]["id"], s["child"]["id"], f"Case {i}") for i in range(n)]
        ids = [c["id"] for c in cases]
        cycle = make_cycle(owner, s["product"]["id"], release_id=s["release"]["id"], case_ids=ids)
        by_case = {cc["case_id"]: cc["id"] for cc in cycle_cases(owner, cycle["id"])}
        return {**s, "cases": cases, "cycle": cycle, "cc": [by_case[c["id"]] for c in cases]}

    def ran(self, s, *statuses):
        for cc, status in zip(s["cc"], statuses, strict=False):
            ok(record(self.live.owner, cc, status=status), 201)

    @test()
    def test_org_report_maps_kpis_trend_and_product_rows(self, suite_parameter):
        s = self.seed()
        self.ran(s, "success", "fail")
        out = self.load({})
        assert out["state"] == "org"
        d = out["data"]
        assert d["org"]["kpis"]["products"] == 1 and d["org"]["kpis"]["successPct"] == 50
        assert d["org"]["trend"]["results"] == 2
        assert (d["org"]["trend"]["totals"]["success"], d["org"]["trend"]["totals"]["fail"]) == (1, 1)
        assert len(d["org"]["trend"]["days"]) == 30 and d["pinDay"] >= 0
        [row] = d["org"]["products"]
        assert (row["id"], row["key"], row["cases"]) == (s["product"]["id"], "PAY", 2)
        assert (row["results"]["success"], row["results"]["fail"], row["successPct"]) == (1, 1, 50)
        assert d["periodKeep"] == {"range": "30d", "from": None, "to": None}
        assert d["periodLabel"] == "last 30 days"
        assert any(p.startswith("/api/v1/orgs/acme/report?from=") and "&tz=" in p for p in out["asked"])
        assert self.load({"ui": "org-hover"})["state"] == "org-hover"
        assert self.load({"ui": "period-custom"})["state"] == "period-custom"

    @test()
    def test_release_readiness_maps_kpis_features_and_drift(self, suite_parameter):
        s = self.seed()
        self.ran(s, "success", "success")
        case = s["cases"][0]
        edited = self.live.owner.patch(
            url(f"/cases/{case['id']}"), json={"title": "New"}, headers={"If-Match": '"1"'}
        )
        assert edited.status_code == 200, edited.text
        out = self.load({"level": "product", "product": "PAY", "release": s["release"]["id"]})
        assert out["state"] == "product"
        r = out["data"]["release"]
        assert (r["id"], r["ver"], r["cycles"]) == (s["release"]["id"], "1.0", 1)
        assert (r["kpis"]["cases"], r["kpis"]["drift"]) == (2, 1)
        [f] = r["features"]
        assert (f["id"], f["path"], f["cases"], f["drift"]) == (s["child"]["id"], "Checkout › Card", 2, 1)
        # the API's verdict: at_risk whenever drift > 0
        assert f["readiness"] == "at risk"
        assert f["driftNote"] == f"{case['key']} v2 is newer than pinned v1"
        assert r["driftExample"] == {"key": case["key"], "from": 1, "to": 2}
        assert [o["id"] for o in r["releases"]] == [s["release"]["id"]]
        assert out["data"]["product"]["key"] == "PAY"
        params = {"level": "product", "product": "PAY", "release": s["release"]["id"], "ui": "pick-release"}
        picked = self.load(params)
        assert picked["state"] == "pick-release" and picked["data"]["release"]["open"] is True

    @test()
    def test_no_release_is_the_whole_product(self, suite_parameter):
        s = self.seed()
        basket = make_feature(self.live.owner, s["product"]["id"], "Basket")
        make_case(self.live.owner, s["product"]["id"], basket["id"], "Add")
        self.ran(s, "success", "fail")
        out = self.load({"level": "product", "product": "PAY", "release": "none"})
        assert out["state"] == "product"
        r = out["data"]["release"]
        assert (r["id"], r["cycles"]) == (None, None)
        assert (r["kpis"]["cases"], r["kpis"]["ran"], r["kpis"]["fail"]) == (3, 2, 1)
        assert [(f["path"], f["readiness"]) for f in r["features"]] == [
            ("Basket", "not started"),
            ("Checkout › Card", "at risk"),
        ]
        whole = [p for p in out["asked"] if "/products/PAY/report" in p]
        assert whole and "release=" not in whole[0]

    @test()
    def test_no_results_is_the_empty_state(self, suite_parameter):
        self.seed()
        out = self.load({"level": "product", "product": "PAY"})
        assert out["state"] == "empty"
        assert (out["data"]["product"]["key"], out["data"]["product"]["cases"]) == ("PAY", 2)

    @test()
    def test_feature_report_maps_cases_kpis_and_history(self, suite_parameter):
        s = self.seed()
        self.ran(s, "success", "fail")
        params = {
            "level": "feature",
            "product": "PAY",
            "feature": s["child"]["id"],
            "release": s["release"]["id"],
        }
        out = self.load(params)
        assert out["state"] == "feature"
        f = out["data"]["feature"]
        assert (f["id"], f["path"], f["name"]) == (s["child"]["id"], "Checkout › Card", "Card")
        assert (f["kpis"]["cases"], f["kpis"]["drift"], f["kpis"]["successPct"]) == (2, 0, 50)
        assert (f["kpis"]["results"]["success"], f["kpis"]["results"]["fail"]) == (1, 1)
        rows = {c["key"]: c for c in f["cases"]}
        first = rows[s["cases"][0]["key"]]
        assert (first["id"], first["result"], first["ranOn"], first["current"]) == (
            s["cases"][0]["id"],
            "success",
            1,
            1,
        )
        assert first["by"] == {"kind": "person", "id": "Olive Owner"} and first["when"]
        assert rows[s["cases"][1]["key"]]["result"] == "fail"
        [run] = f["history"]
        assert (run["ver"], run["successPct"]) == ("1.0", 50)
        assert out["data"]["release"] == {"id": s["release"]["id"], "ver": "1.0"}
        asked = [p for p in out["asked"] if "/features/" in p]
        assert asked and f"release={s['release']['id']}" in asked[0]

    @test()
    def test_custom_period_goes_to_the_server(self, suite_parameter):
        self.seed()
        out = self.load({"range": "custom", "from": "2026-01-01", "to": "2026-01-31"})
        assert out["state"] == "org"
        assert out["data"]["period"]["value"] == "custom" and out["data"]["period"]["applied"] is True
        assert out["data"]["periodKeep"] == {"range": "custom", "from": "2026-01-01", "to": "2026-01-31"}
        assert any("from=2026-01-01&to=2026-01-31" in p for p in out["asked"])
        assert len(out["data"]["org"]["trend"]["days"]) == 31

    @test()
    def test_unknown_release_is_the_raw_404(self, suite_parameter):
        self.seed()
        out = run_js(
            self.live,
            """await h.signIn();
            const params = { level: "product", product: "PAY", release: "nope" };
            const ctx = await h.ctx(params);
            return h.fail((await h.adapter("reports")).load(params, ctx));""",
            "/app?view=reports",
        )
        raw = as_sent(self.live.owner.get(url("/releases/nope")))
        assert body_of(raw)["status"] == 404
        assert out == {"name": "ApiError", "status": 404, "raw": raw}
