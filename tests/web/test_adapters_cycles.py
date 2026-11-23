"""Web adapter for Cycles, run in node against a live server: the empty product, the list with its server-side
status tabs and bulk batches, the new-cycle and bulk wizard states, one cycle's detail (open, closed, and the
refresh-confirm diff, its cases per feature, who closed it), the writes (create, preview, bulk with its name
pattern, assignees and skip drafts, close, reopen, refresh) read back from the server, and raw errors."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_product, ok, url
from tests.execution_seed import edit_steps, make_cycle, record, run_seed
from tests.web.live import LiveServer, as_sent, run_js

URL = "/app?view=cycles"


@Suite(parameters=support.DATABASES)
class WebCyclesAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def js(self, body, params=None):
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps(params or {"product": "PAY"})};
            const ctx = await h.ctx(params);
            const a = await h.adapter("cycles");
            {body}""",
            URL,
        )

    def load(self, params):
        params = {"product": "PAY", **params}
        return self.js("return await a.load(params, ctx);", params)

    @test()
    def test_no_cycles_is_the_empty_state(self, suite_parameter):
        make_product(self.live.owner, "PAY")
        out = self.load({})
        assert out["state"] == "empty"
        assert out["data"]["rows"] == [] and out["data"]["tabs"] == {"open": 0, "closed": 0}
        assert self.load({"ui": "new-cycle"})["state"] == "new-cycle"

    @test()
    def test_list_maps_rows_and_the_status_tab_is_the_servers_filter(self, suite_parameter):
        owner = self.live.owner
        s = run_seed(owner)
        other = make_cycle(
            owner,
            s["product"]["id"],
            name="Staging smoke",
            case_ids=[s["case"]["id"]],
            release_id=s["release"]["id"],
            environment="staging",
        )
        ok(owner.post(url(f"/cycles/{other['id']}/close")))
        out = self.load({})
        assert out["state"] == "list"
        d = out["data"]
        assert d["tabs"] == {"open": 1, "closed": 1}
        assert d["filter"]["status"] == "open"
        assert [r["name"] for r in d["rows"]] == ["Run"]
        assert d["rows"][0]["id"] == s["cycle"]["id"] and d["rows"][0]["results"] == {"untested": 1}
        closed = self.load({"status": "closed"})["data"]["rows"]
        assert [(r["name"], r["release"], r["env"], r["status"]) for r in closed] == [
            ("Staging smoke", "1.0", "staging", "closed")
        ]
        assert {r["name"] for r in self.load({"status": "all"})["data"]["rows"]} == {"Run", "Staging smoke"}
        assert [e["v"] for e in self.load({"status": "closed"})["data"]["envs"]] == ["staging"]
        listed = self.js(
            "await a.load({ product: 'PAY', status: 'closed' }, ctx); "
            "return h.calls.filter((c) => c.path.includes('/cycles?')).map((c) => c.path);"
        )
        assert any("status=closed" in p for p in listed)

    @test()
    def test_new_cycle_state_lists_the_feature_tree(self, suite_parameter):
        s = run_seed(self.live.owner)
        out = self.load({"ui": "new-cycle"})
        assert out["state"] == "new-cycle"
        groups = out["data"]["featureGroups"]
        assert [g["name"] for g in groups] == ["Checkout"]
        assert {f["v"] for f in groups[0]["features"]} == {s["parent"]["id"], s["child"]["id"]}
        assert out["data"]["draft"]["total"] == 0

    @test()
    def test_bulk_wizard_previews_the_release_then_bulk_creates_a_batch(self, suite_parameter):
        s = run_seed(self.live.owner)
        rel = s["release"]["id"]
        pick = self.load({"ui": "bulk-pick-release", "release": rel})
        assert pick["state"] == "bulk-pick-release"
        assert pick["data"]["bulk"]["releaseId"] == rel and pick["data"]["bulk"]["cases"] == 1
        prev = self.load({"ui": "bulk-preview", "release": rel})
        assert prev["state"] == "bulk-preview"
        assert prev["data"]["bulk"]["per"] == "features" and prev["data"]["bulk"]["featureCount"] == 1
        batch = self.js(
            f"""return await a.actions.bulk("{rel}", {{ per: "features", environment: "staging" }}, ctx);"""
        )
        got = ok(self.live.owner.get(url(f"/cycle-batches/{batch['id']}")))
        assert got["environment"] == "staging" and len(got["cycles"]) == 1
        done = self.load({"ui": "bulk-created", "batch": batch["id"]})
        assert done["state"] == "bulk-created"
        assert done["data"]["bulk"]["total"] == 1 and done["data"]["bulk"]["release"] == "1.0"
        rows = self.load({})["data"]["rows"]
        i = next(i for i, r in enumerate(rows) if r.get("kind") == "batch")
        assert rows[i]["id"] == batch["id"] and rows[i]["cycles"] == 1 and rows[i]["per"] == "features"
        assert rows[i + 1]["inBatch"] is True and rows[i + 1]["id"] == got["cycles"][0]["id"]
        assert sum(1 for r in rows if r.get("kind") != "batch") == 2

    @test()
    def test_bulk_sends_the_name_pattern_assignees_and_skip_drafts_and_the_batch_says_who_closed_it(
        self, suite_parameter
    ):
        owner = self.live.owner
        s = run_seed(owner)
        rel, child, me = s["release"]["id"], s["child"]["id"], s["cycle"]["created_by_actor_id"]
        form = {
            "per": "features",
            "environment": "staging",
            "namePattern": "{release} on {env}: {feature}",
            "assignees": {child: me},
            "skipDrafts": True,
        }
        batch = self.js(f"""return await a.actions.bulk("{rel}", {json.dumps(form)}, ctx);""")
        [c] = ok(owner.get(url(f"/cycle-batches/{batch['id']}")))["cycles"]
        assert (c["name"], c["default_assignee_actor_id"]) == (f"1.0 on staging: {s['child']['name']}", me)
        assert sum(c["counts"].values()) == 0  # the seed's one case is a draft
        plain = self.js(
            f"""return await a.actions.bulk("{rel}", {{ per: "features", namePattern: "" }}, ctx);"""
        )
        [d] = plain["cycles"]
        assert d["name"] == f"1.0 · {s['child']['name']}" and sum(d["counts"].values()) == 1
        row = next(r for r in self.load({"status": "all"})["data"]["rows"] if r["id"] == batch["id"])
        assert (row["by"], row["closedBy"]) == ({"kind": "person", "name": me}, None)
        ok(owner.post(url(f"/cycles/{c['id']}/close")))
        row = next(r for r in self.load({"status": "all"})["data"]["rows"] if r["id"] == batch["id"])
        assert row["closedBy"] == {"kind": "person", "name": me}

    @test()
    def test_a_bad_name_pattern_is_refused_raw(self, suite_parameter):
        s = run_seed(self.live.owner)
        rel = s["release"]["id"]
        form = '{ per: "features", namePattern: "{plan}" }'
        out = self.js(f"""return await h.fail(a.actions.bulk("{rel}", {form}, ctx));""")
        body = {
            "mode": "features",
            "environment": None,
            "name_pattern": "{plan}",
            "assignees": {},
            "skip_drafts": False,
        }
        direct = self.live.owner.post(url(f"/releases/{rel}/cycles/bulk"), json=body)
        assert direct.status_code == 422 and out["status"] == 422
        assert out["raw"] == as_sent(direct)

    @test()
    def test_detail_counts_cases_per_feature_and_says_who_closed_it(self, suite_parameter):
        owner = self.live.owner
        s = run_seed(owner)
        cy = self.load({"id": s["cycle"]["id"]})["data"]["cycle"]
        assert [(f["id"], f["cases"]) for f in cy["features"]] == [(s["child"]["id"], 1)]
        assert cy["features"][0]["path"].endswith(s["child"]["name"]) and cy["closedBy"] is None
        closed = ok(owner.post(url(f"/cycles/{s['cycle']['id']}/close")))
        cy = self.load({"id": s["cycle"]["id"]})["data"]["cycle"]
        assert cy["closedBy"] == {"kind": "person", "name": closed["closed_by_actor_id"]}

    @test()
    def test_detail_maps_the_cycle_its_cases_and_their_attempts(self, suite_parameter):
        owner = self.live.owner
        s = run_seed(owner)
        cc = s["cycle_case"]
        defect = {"url": "https://issues.example.com/PAY-1", "key": "PAY-1"}
        assert record(owner, cc["id"], status="fail", defects=[defect]).status_code == 201
        out = self.load({"id": s["cycle"]["id"]})
        assert out["state"] == "detail"
        c = out["data"]["cycle"]
        assert c["id"] == s["cycle"]["id"] and c["status"] == "open" and c["counts"]["fail"] == 1
        [x] = c["cases"]
        mapped = (x["id"], x["key"], x["pinned"], x["newer"], x["status"])
        assert mapped == (cc["id"], s["case"]["key"], 1, 0, "fail")
        assert x["hasResult"] is True and x["attempt"] == 1 and x["note"] == "PAY-1"
        ok(owner.post(url(f"/cycles/{s['cycle']['id']}/close")))
        closed = self.load({"id": s["cycle"]["id"]})
        assert closed["state"] == "closed" and closed["data"]["cycle"]["closedAt"]

    @test()
    def test_refresh_confirm_shows_the_diff_and_refresh_repins(self, suite_parameter):
        owner = self.live.owner
        s = run_seed(owner)
        edit_steps(owner, s["case"])
        cid, cc = s["cycle"]["id"], s["cycle_case"]["id"]
        out = self.load({"id": cid, "ui": "refresh-confirm"})
        assert out["state"] == "refresh-confirm"
        f = out["data"]["refresh"]
        assert (f["id"], f["from"], f["to"], f["results"]) == (cc, 1, 2, 0)
        assert f["before"] == "The cart opens" and f["after"] == "It opens"
        assert self.load({"id": cid})["data"]["cycle"]["cases"][0]["newer"] == 2
        self.js(f"""return await a.actions.refresh("{cc}", ctx);""")
        [back] = ok(owner.get(url(f"/cycles/{cid}/cases")))["items"]
        assert back["case_version"] == 2
        assert self.load({"id": cid, "ui": "refresh-confirm"})["state"] == "detail"

    @test()
    def test_a_case_with_a_result_can_be_refreshed_and_keeps_it(self, suite_parameter):
        owner = self.live.owner
        s = run_seed(owner)
        cid, cc = s["cycle"]["id"], s["cycle_case"]["id"]
        assert record(owner, cc, status="fail").status_code == 201
        edit_steps(owner, s["case"])
        out = self.load({"id": cid, "ui": "refresh-confirm", "cc": cc})
        assert out["state"] == "refresh-confirm"
        f = out["data"]["refresh"]
        assert (f["id"], f["from"], f["to"], f["results"]) == (cc, 1, 2, 1)
        assert self.load({"id": cid, "ui": "refresh-confirm"})["data"]["refresh"]["id"] == cc
        self.js(f"""return await a.actions.refresh("{cc}", ctx);""")
        [back] = ok(owner.get(url(f"/cycles/{cid}/cases")))["items"]
        assert (back["case_version"], back["status"]) == (2, "untested")

    @test()
    def test_create_preview_close_and_reopen_reach_the_server(self, suite_parameter):
        owner = self.live.owner
        s = run_seed(owner)
        child, rel = s["child"]["id"], s["release"]["id"]
        p = self.js(f"""return await a.actions.preview(["{child}"], ctx, "PAY");""")
        assert p["total"] == 1
        made = self.js(f"""return await a.actions.create({{ name: "Card regression", featureIds: ["{child}"],
            releaseId: "{rel}", environment: "prod-eu", assigneeId: null }}, ctx, "PAY");""")
        got = ok(owner.get(url(f"/cycles/{made['id']}")))
        assert (got["name"], got["release_id"], got["environment"]) == ("Card regression", rel, "prod-eu")
        assert sum(got["counts"].values()) == got["counts"]["untested"] == 1, got["counts"]
        self.js(f"""return await a.actions.close("{made["id"]}", ctx);""")
        assert ok(owner.get(url(f"/cycles/{made['id']}")))["status"] == "closed"
        self.js(f"""return await a.actions.reopen("{made["id"]}", ctx);""")
        assert ok(owner.get(url(f"/cycles/{made['id']}")))["status"] == "open"

    @test()
    def test_refresh_on_a_closed_cycle_is_refused_raw(self, suite_parameter):
        owner = self.live.owner
        s = run_seed(owner)
        cc = s["cycle_case"]["id"]
        edit_steps(owner, s["case"])
        ok(owner.post(url(f"/cycles/{s['cycle']['id']}/close")))
        out = self.js(f"""return await h.fail(a.actions.refresh("{cc}", ctx));""")
        direct = owner.post(url(f"/cycle-cases/{cc}/refresh-version"))
        assert out["name"] == "ApiError" and out["status"] == direct.status_code >= 400
        assert out["raw"] == as_sent(direct)
