"""T6 reports: release status per case, readiness, stale results, NULLS LAST, and org isolation.
F5: period filters, trends, org KPIs, the whole product and feature history."""

from datetime import UTC, datetime

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.api.v1 import reports as reports_module
from test_junkie_tcms.api.v1 import results as results_module
from tests import support
from tests.catalog_seed import make_feature, make_product, make_release, ok, seed, url
from tests.execution_seed import cycle_cases, make_case, make_cycle, record
from tests.support import PASSWORD, login


def release_seed(owner, key: str = "PAY", n: int = 3, org: str = "acme") -> dict:
    """The catalog seed plus `n` cases under the release's feature, all in one cycle of the release."""
    s = seed(owner, key, org)
    cases = [make_case(owner, s["product"]["id"], s["child"]["id"], f"Case {i}", org) for i in range(n)]
    cycle = make_cycle(
        owner, s["product"]["id"], org, release_id=s["release"]["id"], case_ids=[c["id"] for c in cases]
    )
    by_case = {cc["case_id"]: cc["id"] for cc in cycle_cases(owner, cycle["id"], org)}
    return {**s, "cases": cases, "cycle": cycle, "cc": [by_case[c["id"]] for c in cases]}


def report(client, release: str, org: str = "acme") -> dict:
    return ok(client.get(url(f"/releases/{release}/report", org)))


def counts(r: dict, *names: str) -> tuple:
    return tuple(r["counts"][n] for n in names)


@Suite(parameters=support.DATABASES)
class Reports:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    @test()
    def test_release_report_counts_pass_fail_blocked(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner)
        ok(record(owner, s["cc"][0], status="success"), 201)
        ok(record(owner, s["cc"][1], status="fail"), 201)
        ok(record(owner, s["cc"][2], status="skip", comment={"markdown": "Blocked by BUG-7"}), 201)
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "fail", "skip", "untested", "total") == (1, 1, 1, 0, 3)
        assert r["ready"] is False
        assert r["release"]["id"] == s["release"]["id"]
        [feature] = r["features"]
        assert (feature["feature_id"], feature["name"], feature["counts"]["total"]) == (
            s["child"]["id"],
            "Card",
            3,
        )

    @test()
    def test_ready_only_when_nothing_failed_or_untested(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        ok(record(owner, s["cc"][0], status="success"), 201)
        assert report(owner, s["release"]["id"])["ready"] is False
        ok(record(owner, s["cc"][1], status="success"), 201)
        assert report(owner, s["release"]["id"])["ready"] is True

    @test()
    def test_empty_release_is_not_ready(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        r = make_release(owner, s["product"]["id"], "2.0")
        out = report(owner, r["id"])
        assert (out["counts"]["total"], out["ready"]) == (0, False)

    @test()
    def test_case_in_no_cycle_is_untested_and_not_in_cycle(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        make_case(owner, s["product"]["id"], s["child"]["id"], "Forgotten")
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "untested", "not_in_cycle", "total") == (1, 1, 1, 2)
        assert r["ready"] is False

    @test()
    def test_result_on_older_case_version_is_untested_and_stale(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        assert report(owner, s["release"]["id"])["ready"] is True
        case = s["cases"][0]
        edited = owner.patch(
            url(f"/cases/{case['id']}"), json={"title": "Changed"}, headers={"If-Match": '"1"'}
        )
        ok(edited)
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "untested", "stale", "total") == (0, 1, 1, 1)
        assert r["ready"] is False
        items = ok(
            owner.get(url(f"/features/{s['child']['id']}/report"), params={"release": s["release"]["id"]})
        )["items"]
        assert (items[0]["status"], items[0]["stale"]) == ("untested", True)

    @test()
    def test_unrun_row_in_newer_cycle_does_not_override_a_result(self, suite_parameter):
        """NULLS LAST: an unrun cycle case sorts after a result on Postgres and SQLite alike."""
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="fail"), 201)
        make_cycle(
            owner,
            s["product"]["id"],
            name="Rerun",
            release_id=s["release"]["id"],
            case_ids=[s["cases"][0]["id"]],
        )
        assert counts(report(owner, s["release"]["id"]), "fail", "untested") == (1, 0)

    @test()
    def test_newest_result_across_cycles_wins(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="fail"), 201)
        rerun = make_cycle(
            owner,
            s["product"]["id"],
            name="Rerun",
            release_id=s["release"]["id"],
            case_ids=[s["cases"][0]["id"]],
        )
        [cc] = cycle_cases(owner, rerun["id"])
        ok(record(owner, cc["id"], status="success"), 201)
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "fail") == (1, 0)
        assert r["ready"] is True

    @test()
    def test_cycle_outside_the_release_does_not_count(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        other = make_cycle(owner, s["product"]["id"], name="Ad hoc", case_ids=[s["cases"][0]["id"]])
        [cc] = cycle_cases(owner, other["id"])
        ok(record(owner, cc["id"], status="fail"), 201)
        assert counts(report(owner, s["release"]["id"]), "fail", "untested") == (0, 1)

    @test()
    def test_release_feature_with_no_cases_has_a_row_and_blocks_ready(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        empty = make_feature(owner, s["product"]["id"], "Empty")
        features = url(f"/releases/{s['release']['id']}/features")
        ok(owner.put(features, json={"feature_ids": [s["child"]["id"], empty["id"]]}))
        r = report(owner, s["release"]["id"])
        assert [(f["name"], f["in_release"], f["counts"]["total"], f["ready"]) for f in r["features"]] == [
            ("Card", True, 1, True),
            ("Empty", True, 0, False),
        ]
        assert r["ready"] is False
        product = ok(owner.get(url(f"/products/{s['product']['id']}/report")))
        assert product["releases"][0]["ready"] is False
        ok(owner.put(features, json={"feature_ids": [s["child"]["id"]]}))
        assert report(owner, s["release"]["id"])["ready"] is True

    @test()
    def test_cycle_case_of_a_feature_outside_the_release_is_flagged(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        basket = make_feature(owner, s["product"]["id"], "Basket")
        case = make_case(owner, s["product"]["id"], basket["id"], "Add to basket")
        regression = make_cycle(
            owner, s["product"]["id"], name="Regression", release_id=s["release"]["id"], case_ids=[case["id"]]
        )
        [cc] = cycle_cases(owner, regression["id"])
        ok(record(owner, s["cc"][0], status="success"), 201)
        ok(record(owner, cc["id"], status="success"), 201)
        r = report(owner, s["release"]["id"])
        assert [(f["name"], f["in_release"], f["counts"]["total"]) for f in r["features"]] == [
            ("Card", True, 1),
            ("Basket", False, 1),
        ]
        assert (r["counts"]["total"], r["ready"]) == (2, True)
        ok(record(owner, cc["id"], status="fail"), 201)
        r = report(owner, s["release"]["id"])
        assert (r["features"][1]["ready"], r["ready"]) == (False, False)

    @test()
    def test_sub_feature_cases_count_once_in_the_nearest_release_feature(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        for cc in s["cc"]:
            ok(record(owner, cc, status="success"), 201)
        features = url(f"/releases/{s['release']['id']}/features")
        ok(owner.put(features, json={"feature_ids": [s["parent"]["id"]]}))
        r = report(owner, s["release"]["id"])
        assert [(f["name"], f["counts"]["total"]) for f in r["features"]] == [("Checkout", 2)]
        assert r["ready"] is True
        ok(owner.put(features, json={"feature_ids": [s["parent"]["id"], s["child"]["id"]]}))
        r = report(owner, s["release"]["id"])
        rows = [(f["name"], f["in_release"], f["counts"]["total"], f["ready"]) for f in r["features"]]
        assert rows == [("Card", True, 2, True), ("Checkout", True, 0, True)]
        assert (r["counts"]["total"], r["ready"]) == (2, True)

    @test()
    def test_archived_release_feature_needs_no_case(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        old = make_feature(owner, s["product"]["id"], "Old")
        features = url(f"/releases/{s['release']['id']}/features")
        ok(owner.put(features, json={"feature_ids": [s["child"]["id"], old["id"]]}))
        assert report(owner, s["release"]["id"])["ready"] is False
        ok(owner.post(url(f"/features/{old['id']}/archive")))
        r = report(owner, s["release"]["id"])
        assert [f["name"] for f in r["features"]] == ["Card"]
        assert r["ready"] is True

    @test()
    def test_product_report_lists_releases_but_not_cancelled(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        gone = make_release(owner, s["product"]["id"], "0.9")
        ok(owner.patch(url(f"/releases/{gone['id']}"), json={"status": "cancelled"}))
        out = ok(owner.get(url(f"/products/{s['product']['id']}/report")))
        assert out["product_key"] == "PAY"
        assert [r["release"]["id"] for r in out["releases"]] == [s["release"]["id"]]
        assert out["releases"][0]["ready"] is True
        one = ok(owner.get(url(f"/products/{s['product']['id']}/report"), params={"release": gone["id"]}))
        assert [r["release"]["id"] for r in one["releases"]] == [gone["id"]]

    @test()
    def test_product_report_refuses_another_products_release(self, suite_parameter):
        owner = self.env.owner
        a = seed(owner, "AAA")
        b = seed(owner, "BBB")
        r = owner.get(url(f"/products/{a['product']['id']}/report"), params={"release": b["release"]["id"]})
        assert r.status_code == 422, r.text

    @test()
    def test_org_report_filters_by_release_status(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        out = ok(owner.get(url("/report")))
        [p] = out["products"]
        assert [r["release"]["id"] for r in p["releases"]] == [s["release"]["id"]]
        ok(owner.patch(url(f"/releases/{s['release']['id']}"), json={"status": "released"}))
        assert ok(owner.get(url("/report")))["products"][0]["releases"] == []
        out = ok(owner.get(url("/report"), params={"release_status": "released"}))
        assert [r["release"]["id"] for r in out["products"][0]["releases"]] == [s["release"]["id"]]
        assert owner.get(url("/report"), params={"release_status": "shipped"}).status_code == 422

    @test()
    def test_feature_report_pages_by_case_number(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=3)
        ok(record(owner, s["cc"][1], status="fail"), 201)
        path = url(f"/features/{s['parent']['id']}/report")
        first = ok(owner.get(path, params={"release": s["release"]["id"], "limit": 2}))
        assert [i["key"] for i in first["items"]] == ["PAY-1", "PAY-2"]
        assert first["items"][1]["status"] == "fail"
        assert first["counts"]["total"] == 3
        rest = ok(
            owner.get(
                path, params={"release": s["release"]["id"], "limit": 2, "cursor": first["next_cursor"]}
            )
        )
        assert ([i["key"] for i in rest["items"]], rest["next_cursor"]) == (["PAY-3"], None)

    @test()
    def test_feature_report_refuses_another_products_release(self, suite_parameter):
        owner = self.env.owner
        a = seed(owner, "AAA")
        b = seed(owner, "BBB")
        r = owner.get(url(f"/features/{a['child']['id']}/report"), params={"release": b["release"]["id"]})
        assert r.status_code == 422, r.text

    @test()
    def test_cycle_report_counts(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        ok(record(owner, s["cc"][0], status="error"), 201)
        out = ok(owner.get(url(f"/cycles/{s['cycle']['id']}/report")))
        assert (out["counts"]["error"], out["counts"]["untested"], out["total"]) == (1, 1, 2)

    @test()
    def test_reports_are_org_isolated(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        globex = self.env.client()
        login(globex, "other@example.com", PASSWORD)
        make_product(globex, "GLX", org="globex")
        for path, params in (
            (f"/releases/{s['release']['id']}/report", None),
            (f"/features/{s['child']['id']}/report", {"release": s["release"]["id"]}),
            (f"/cycles/{s['cycle']['id']}/report", None),
            (f"/products/{s['product']['id']}/report", None),
        ):
            assert globex.get(url(path, "globex"), params=params).status_code == 404, path
        assert [p["product_key"] for p in ok(globex.get(url("/report", "globex")))["products"]] == ["GLX"]
        assert [p["product_key"] for p in ok(owner.get(url("/report")))["products"]] == ["PAY"]

    @test()
    def test_product_limited_token_sees_only_its_product(self, suite_parameter):
        owner = self.env.owner
        a = release_seed(owner, "AAA", n=1)
        b = release_seed(owner, "BBB", n=1)
        token = ok(
            owner.post(
                url("/tokens"),
                json={"name": "a-only", "scopes": ["read"], "product_ids": [a["product"]["id"]]},
            ),
            201,
        )["token"]
        client = self.env.bearer(token)
        assert [p["product_key"] for p in ok(client.get(url("/report")))["products"]] == ["AAA"]
        assert client.get(url(f"/releases/{b['release']['id']}/report")).status_code == 404
        assert client.get(url(f"/releases/{a['release']['id']}/report")).status_code == 200

    # F5: period, trend, KPIs, the whole product and feature history.

    def at(self, when: datetime) -> None:
        """Record every later result at `when`."""
        self.env.patch(results_module, "utcnow", lambda: when)

    def agent(self) -> object:
        owner = self.env.owner
        bot = ok(owner.post(url("/agents"), json={"name": "bot", "role": "admin"}), 201)
        body = {"name": "bot", "scopes": ["read", "write:execution"], "actor_id": bot["id"]}
        return self.env.bearer(ok(owner.post(url("/tokens"), json=body), 201)["token"])

    @test()
    def test_period_refuses_a_bad_zone_reversed_or_overlong_range(self, suite_parameter):
        owner = self.env.owner
        for params in (
            {"tz": "Mars/Olympus"},
            {"from": "2026-11-10", "to": "2026-11-09"},
            {"from": "2025-01-01", "to": "2026-01-02"},
        ):
            assert owner.get(url("/report"), params=params).status_code == 422, params
        assert owner.get(url("/report"), params={"from": "2025-01-01", "to": "2026-01-01"}).status_code == 200

    @test()
    def test_default_period_is_30_days_ending_today_in_tz(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        self.env.patch(reports_module, "utcnow", lambda: datetime(2026, 11, 12, 5, 0, tzinfo=UTC))
        path = url(f"/releases/{s['release']['id']}/report")
        days = ok(owner.get(path))["trend"]["days"]
        assert (len(days), days[0]["date"], days[-1]["date"]) == (30, "2026-10-14", "2026-11-12")
        days = ok(owner.get(path, params={"tz": "America/Los_Angeles"}))["trend"]["days"]
        assert days[-1]["date"] == "2026-11-11"

    @test()
    def test_trend_buckets_by_day_in_tz_zero_fills_and_finds_the_peak(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=3)
        self.at(datetime(2026, 11, 11, 7, 30, tzinfo=UTC))  # Tue Nov 10, 11:30 PM PT
        ok(record(owner, s["cc"][0], status="success"), 201)
        ok(record(owner, s["cc"][1], status="fail"), 201)
        self.at(datetime(2026, 11, 11, 20, 0, tzinfo=UTC))
        ok(record(self.agent(), s["cc"][2], status="skip", comment={"markdown": "Blocked"}), 201)
        path = url(f"/releases/{s['release']['id']}/report")
        window = {"from": "2026-11-09", "to": "2026-11-12"}
        pt = ok(owner.get(path, params={**window, "tz": "America/Los_Angeles"}))["trend"]
        assert [(d["date"], d["success"], d["fail"], d["skip"]) for d in pt["days"]] == [
            ("2026-11-09", 0, 0, 0),
            ("2026-11-10", 1, 1, 0),
            ("2026-11-11", 0, 0, 1),
            ("2026-11-12", 0, 0, 0),
        ]
        assert (pt["total"], pt["peak_day"], pt["by_agents_pct"]) == (
            3,
            {"date": "2026-11-10", "total": 2},
            33,
        )
        utc = ok(owner.get(path, params=window))["trend"]
        assert [d["date"] for d in utc["days"] if d["success"] or d["fail"] or d["skip"]] == ["2026-11-11"]
        none = ok(owner.get(path, params={"from": "2026-11-01", "to": "2026-11-02"}))["trend"]
        assert (none["total"], none["peak_day"], none["by_agents_pct"]) == (0, None, None)

    @test()
    def test_success_rate_counts_skip_ignore_and_cancel_as_ran(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=5)
        for cc, status in zip(s["cc"], ("success", "success", "skip", "ignore"), strict=False):
            ok(record(owner, cc, status=status, comment={"markdown": "Why"}), 201)
        kpis = report(owner, s["release"]["id"])["kpis"]
        assert kpis == {"cases": 5, "ran": 4, "fail": 0, "error": 0, "skip": 1, "drift": 0, "success_rate": 50}

    @test()
    def test_feature_verdict_and_drift(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)

        def row() -> dict:
            [f] = report(owner, s["release"]["id"])["features"]
            return f

        assert (row()["verdict"], row()["path"]) == ("not_started", "Checkout › Card")
        ok(record(owner, s["cc"][0], status="success"), 201)
        assert row()["verdict"] == "in_progress"
        ok(record(owner, s["cc"][1], status="success"), 201)
        assert (row()["verdict"], row()["drift"], row()["drifted"]) == ("ready", 0, [])
        case = s["cases"][0]
        ok(owner.patch(url(f"/cases/{case['id']}"), json={"title": "New"}, headers={"If-Match": '"1"'}))
        f = row()
        assert (f["verdict"], f["drift"]) == ("at_risk", 1)
        assert f["drifted"] == [{"key": "PAY-1", "ran_version": 1, "current_version": 2}]
        assert report(owner, s["release"]["id"])["kpis"]["drift"] == 1

    @test()
    def test_fail_or_error_makes_a_feature_at_risk(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        ok(record(owner, s["cc"][0], status="error"), 201)
        assert report(owner, s["release"]["id"])["features"][0]["verdict"] == "at_risk"

    @test()
    def test_org_kpis_and_product_rows(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, child = s["product"]["id"], s["child"]["id"]
        cases = [
            make_case(owner, p, child, "Ready auto", status="ready", automation="automated"),
            make_case(owner, p, child, "Ready manual", status="ready"),
            make_case(owner, p, child, "Draft"),
        ]
        cycle = make_cycle(owner, p, case_ids=[c["id"] for c in cases])
        ccs = {cc["case_id"]: cc["id"] for cc in cycle_cases(owner, cycle["id"])}
        self.at(datetime(2026, 11, 11, 12, 0, tzinfo=UTC))
        ok(record(owner, ccs[cases[0]["id"]], status="success"), 201)
        ok(record(self.agent(), ccs[cases[1]["id"]], status="cancel"), 201)
        out = ok(owner.get(url("/report"), params={"from": "2026-11-01", "to": "2026-11-30"}))
        [row] = out["products"]
        assert (row["name"], row["cases"], row["automated_pct"], row["open_cycles"]) == ("PAY product", 3, 33, 1)
        assert counts({"counts": row["results"]}, "success", "cancel", "untested", "total") == (1, 1, 1, 3)
        assert row["success_rate"] == 50
        assert out["kpis"] == {
            "ready_cases": 2,
            "products": 1,
            "success_rate": 50,
            "automated_pct": 33,
            "open_cycles": 1,
            "open_untested": 1,
        }
        assert (out["trend"]["total"], out["trend"]["by_agents_pct"]) == (2, 50)
        ok(owner.post(url(f"/cycles/{cycle['id']}/close")))
        out = ok(owner.get(url("/report"), params={"from": "2026-11-01", "to": "2026-11-30"}))
        assert (out["kpis"]["open_cycles"], out["kpis"]["open_untested"]) == (0, 0)
        assert counts({"counts": out["products"][0]["results"]}, "untested", "total") == (0, 2)
        later = ok(owner.get(url("/report"), params={"from": "2026-11-20", "to": "2026-11-21"}))
        assert (later["kpis"]["success_rate"], later["trend"]["total"]) == (None, 0)

    @test()
    def test_product_report_without_release_has_the_whole_product(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        basket = make_feature(owner, s["product"]["id"], "Basket")
        make_case(owner, s["product"]["id"], basket["id"], "Add to basket")
        self.at(datetime(2026, 11, 11, 12, 0, tzinfo=UTC))
        ok(record(owner, s["cc"][0], status="success"), 201)
        ok(record(owner, s["cc"][1], status="fail"), 201)
        path = url(f"/products/{s['product']['id']}/report")
        out = ok(owner.get(path, params={"from": "2026-11-11", "to": "2026-11-11"}))
        whole = out["whole"]
        assert whole["kpis"] == {"cases": 3, "ran": 2, "fail": 1, "error": 0, "skip": 0, "drift": 0, "success_rate": 50}
        assert [(f["path"], f["counts"]["total"], f["in_release"], f["verdict"]) for f in whole["features"]] == [
            ("Basket", 1, False, "not_started"),
            ("Checkout › Card", 2, False, "at_risk"),
        ]
        assert out["trend"]["total"] == 2
        before = ok(owner.get(path, params={"from": "2026-11-01", "to": "2026-11-10"}))["whole"]
        assert (before["kpis"]["ran"], before["kpis"]["cases"]) == (0, 3)
        one = ok(owner.get(path, params={"release": s["release"]["id"], "from": "2026-11-11", "to": "2026-11-11"}))
        assert (one["whole"], one["trend"]["total"]) == (None, 2)

    @test()
    def test_feature_items_carry_the_result_and_the_stale_one(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        bot = self.agent()
        defect = {"url": "https://bugs.example.com/LAB-412", "key": "LAB-412"}
        ok(record(bot, s["cc"][0], status="fail"), 201)
        ok(record(bot, s["cc"][0], status="success", comment={"markdown": "Passes on retry"}, defects=[defect]), 201)
        path = url(f"/features/{s['child']['id']}/report")
        params = {"release": s["release"]["id"]}
        [item] = ok(owner.get(path, params=params))["items"]
        assert (item["status"], item["ran_version"], item["current_version"]) == ("success", 1, 1)
        assert (item["actor"], item["attempt"], item["comment"]) == ({"kind": "agent", "name": "bot"}, 2, "Passes on retry")
        assert item["defects"] == [defect]
        assert (item["last_result"]["status"], item["last_result"]["version"]) == ("success", 1)
        case = s["cases"][0]
        ok(owner.patch(url(f"/cases/{case['id']}"), json={"title": "New"}, headers={"If-Match": '"1"'}))
        report_ = ok(owner.get(path, params=params))
        [item] = report_["items"]
        assert (item["status"], item["stale"], item["ran_version"], item["actor"]) == ("untested", True, None, None)
        last = item["last_result"]
        assert (last["status"], last["version"], last["attempt"], last["actor"]["name"]) == ("success", 1, 2, "bot")
        assert (report_["kpis"]["drift"], item["current_version"]) == (1, 2)

    @test()
    def test_feature_report_without_release_uses_the_period(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        self.at(datetime(2026, 11, 11, 12, 0, tzinfo=UTC))
        ok(record(owner, s["cc"][0], status="success"), 201)
        path = url(f"/features/{s['parent']['id']}/report")
        inside = ok(owner.get(path, params={"from": "2026-11-11", "to": "2026-11-11"}))
        assert (inside["release"], inside["items"][0]["status"]) == (None, "success")
        outside = ok(owner.get(path, params={"from": "2026-11-12", "to": "2026-11-13"}))
        assert outside["items"][0]["status"] == "untested"

    @test()
    def test_feature_history_is_the_last_runs_whatever_the_period(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        self.at(datetime(2026, 10, 6, 12, 0, tzinfo=UTC))
        ok(record(owner, s["cc"][0], status="success"), 201)
        ok(record(owner, s["cc"][1], status="fail"), 201)
        rerun = make_cycle(
            owner, s["product"]["id"], name="Rerun", environment="staging", case_ids=[c["id"] for c in s["cases"]]
        )
        self.at(datetime(2026, 10, 30, 12, 0, tzinfo=UTC))
        for cc in cycle_cases(owner, rerun["id"]):
            ok(record(owner, cc["id"], status="success"), 201)
        out = ok(owner.get(url(f"/features/{s['child']['id']}/report"), params={"from": "2026-11-20", "to": "2026-11-21"}))
        runs = [(h["cycle_id"], h["release_version"], h["environment"], h["success_rate"]) for h in out["history"]]
        assert runs == [(rerun["id"], None, "staging", 100), (s["cycle"]["id"], "1.0", None, 50)]
        assert out["history"][1]["counts"]["fail"] == 1
        assert out["history"][0]["at"].startswith("2026-10-30T12:00:00")
        assert out["kpis"] == {"cases": 2, "success": 0, "success_rate_last5": 75, "drift": 0}

    @test()
    def test_f5_keeps_every_older_report_key(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        old = {
            f"/releases/{s['release']['id']}/report": ({"release", "counts", "ready", "features"}, None),
            f"/products/{s['product']['id']}/report": ({"product_id", "product_key", "releases"}, None),
            "/report": ({"products"}, None),
            f"/features/{s['child']['id']}/report": (
                {"feature_id", "release", "counts", "items", "next_cursor"},
                {"release": s["release"]["id"]},
            ),
        }
        for path, (keys, params) in old.items():
            assert keys <= set(ok(owner.get(url(path), params=params))), path
        [item] = ok(owner.get(url(f"/features/{s['child']['id']}/report"), params={"release": s["release"]["id"]}))[
            "items"
        ]
        assert {"id", "key", "title", "feature_id", "status", "stale", "cycle_id", "last_result_at"} <= set(item)
        [f] = report(owner, s["release"]["id"])["features"]
        assert {"feature_id", "name", "in_release", "counts", "ready"} <= set(f)
