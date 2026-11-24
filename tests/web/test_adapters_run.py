"""Web adapter for the Run screen, run in node against a live server: the first untested case with its pinned
steps (in-progress), a case with an earlier attempt (retest), the toast after a save (submitted), a cycle with
nothing left (complete), the skip reasons and the build menu from the builds recorded, the writes (submit a
result with every step status, a skip reason and the build; attach evidence) read back from the server, and
raw errors."""

import base64
import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import ok, seed, url
from tests.execution_seed import STEPS, cycle_cases, make_case, make_cycle, record
from tests.web.live import LiveServer, as_sent, run_js


def world(owner) -> dict:
    """PAY's Card feature with two two-step cases in one open cycle on release 1.0, environment staging."""
    s = seed(owner)
    pid, child = s["product"]["id"], s["child"]["id"]
    pre = {"markdown": "Test mode on"}
    first = make_case(owner, pid, child, "Pay by card", steps=STEPS, preconditions=pre)
    second = make_case(owner, pid, child, "Pay by voucher", steps=STEPS)
    cycle = make_cycle(
        owner,
        pid,
        name="Card run",
        case_ids=[first["id"], second["id"]],
        release_id=s["release"]["id"],
        environment="staging",
    )
    return {**s, "cycle": cycle, "ccs": cycle_cases(owner, cycle["id"], sort="position")}


@Suite(parameters=support.DATABASES)
class WebRunAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def js(self, body, params):
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps(params)};
            const ctx = await h.ctx(params);
            const a = await h.adapter("run");
            {body}""",
            "/app?view=run",
        )

    def load(self, params):
        return self.js("return await a.load(params, ctx);", {"product": "PAY", **params})

    @test()
    def test_in_progress_opens_the_first_untested_case_with_its_pinned_steps(self, suite_parameter):
        w = world(self.live.owner)
        out = self.load({"id": w["cycle"]["id"]})
        assert out["state"] == "in-progress"
        d = out["data"]
        assert d["cycle"] == {
            "id": w["cycle"]["id"],
            "queue": "Card run",
            "version": "1.0",
            "environment": "staging",
            "releaseId": w["release"]["id"],
            "status": "open",
        }
        assert [(q["id"], q["title"], q["status"]) for q in d["queue"]] == [
            (w["ccs"][0]["id"], "Pay by card", "untested"),
            (w["ccs"][1]["id"], "Pay by voucher", "untested"),
        ]
        c = d["case"]
        mapped = (c["id"], c["pin"], c["newer"], c["attempt"], c["preconditions"])
        assert mapped == (w["ccs"][0]["id"], 1, 0, 1, "Test mode on")
        assert [(s["action"], s["expected"]) for s in c["steps"]] == [
            ("Open the cart", "The cart opens"),
            ("Pay by card", "The order is paid"),
        ]
        assert d["current"] == {"q": 0, "step": 0, "res": []} and d["previous"] is None
        assert self.load({"id": w["cycle"]["id"], "ui": "help"})["state"] == "help"

    @test()
    def test_a_case_with_an_attempt_is_a_retest_and_a_done_cycle_is_complete(self, suite_parameter):
        owner = self.live.owner
        w = world(owner)
        first, second = w["ccs"]
        defect = {"url": "https://issues.example.com/PAY-7", "key": "PAY-7"}
        note = {"markdown": "Spinner forever"}
        assert record(owner, first["id"], status="fail", comment=note, defects=[defect]).status_code == 201
        nxt = self.load({"id": w["cycle"]["id"]})
        assert nxt["state"] == "in-progress" and nxt["data"]["case"]["id"] == second["id"]
        out = self.load({"id": w["cycle"]["id"], "cc": first["id"]})
        assert out["state"] == "retest"
        p = out["data"]["previous"]
        assert (p["status"], p["note"], p["defectKey"]) == ("fail", "Spinner forever", "PAY-7")
        assert out["data"]["case"]["attempt"] == 2 and out["data"]["current"]["q"] == 0
        assert record(owner, second["id"], status="success").status_code == 201
        done = self.load({"id": w["cycle"]["id"]})
        assert done["state"] == "complete"
        assert [q["status"] for q in done["data"]["queue"]] == ["fail", "success"]

    @test()
    def test_submit_and_attach_reach_the_server_and_submitted_shows_the_save(self, suite_parameter):
        owner = self.live.owner
        w = world(owner)
        first = w["ccs"][0]
        steps = [s["id"] for s in ok(owner.get(url(f"/cases/{first['case_id']}/versions/1")))["steps"]]
        content = base64.b64encode(b"evidence").decode()
        out = self.js(
            f"""const file = {{ filename: "shot.png", mime: "image/png", content_base64: "{content}" }};
            const f = await a.actions.attach("PAY", file, ctx);
            const r = await a.actions.submit("{first["id"]}", {{
              status: "fail", comment: {{ markdown: "Broke" }}, duration_ms: 1200,
              steps: [{{ step_id: "{steps[0]}", status: "success" }},
                      {{ step_id: "{steps[1]}", status: "fail", actual: {{ markdown: "No receipt" }},
                         attachment_ids: [f.id] }}],
              defects: [{{ url: "https://issues.example.com/PAY-9", key: "PAY-9" }}] }}, ctx);
            return {{ f, r }};""",
            {"product": "PAY"},
        )
        got = owner.get(url(f"/attachments/{out['f']['id']}"))
        assert got.status_code == 200 and got.content == b"evidence"
        [res] = ok(owner.get(url(f"/cycle-cases/{first['id']}/results")))["items"]
        assert res["id"] == out["r"]["id"] and res["status"] == "fail" and res["duration_ms"] == 1200
        assert [s["status"] for s in res["steps"]] == ["success", "fail"]
        assert res["steps"][1]["attachment_ids"] == [out["f"]["id"]]
        assert [d["key"] for d in res["defects"]] == ["PAY-9"]
        shown = self.load({"id": w["cycle"]["id"], "done": first["id"], "ui": "submitted"})
        assert shown["state"] == "submitted"
        assert shown["data"]["saved"] == {
            "key": first["key"],
            "status": "fail",
            "attempt": 1,
            "defects": 1,
            "files": 1,
            "via": res["via"],
        }
        assert shown["data"]["case"]["id"] == w["ccs"][1]["id"]

    @test()
    def test_the_build_menu_lists_the_recorded_builds_and_the_case_keeps_its_last_build(
        self, suite_parameter
    ):
        owner = self.live.owner
        w = world(owner)
        first, second = w["ccs"]
        fresh = self.load({"id": w["cycle"]["id"]})["data"]
        assert [o["v"] for o in fresh["builds"]] == [""] and fresh["case"]["build"] == ""
        assert [o["v"] for o in fresh["skipReasons"] if isinstance(o, dict) and "v" in o] == [
            "defect",
            "env",
            "data",
            "dep",
            "na_env",
            "flag",
            "other",
        ]
        assert record(owner, second["id"], status="success", build="1.4.3").status_code == 201
        new = self.load({"id": w["cycle"]["id"]})["data"]
        assert new["case"]["id"] == first["id"] and new["case"]["build"] == "1.4.3"  # the newest recorded
        assert record(owner, first["id"], status="fail", build="1.4.2").status_code == 201
        assert record(owner, second["id"], status="success", build="1.4.4").status_code == 201
        d = self.load({"id": w["cycle"]["id"], "cc": first["id"]})["data"]
        assert [o["v"] for o in d["builds"] if isinstance(o, dict) and "v" in o] == [
            "1.4.4",
            "1.4.2",
            "1.4.3",
            "",
        ]
        assert d["case"]["build"] == "1.4.2"  # its last attempt's

    @test()
    def test_submit_sends_every_step_status_the_skip_reason_and_the_build(self, suite_parameter):
        owner = self.live.owner
        w = world(owner)
        first = w["ccs"][0]
        steps = [s["id"] for s in ok(owner.get(url(f"/cases/{first['case_id']}/versions/1")))["steps"]]
        self.js(
            f"""return await a.actions.submit("{first["id"]}", {{
              status: "skip", skip_reason: "env", build: "2.0.1",
              steps: [{{ step_id: "{steps[0]}", status: "ignore" }},
                      {{ step_id: "{steps[1]}", status: "cancel" }}],
              defects: [{{ url: "https://issues.example.com/OPS-3" }}] }}, ctx);""",
            {"product": "PAY"},
        )
        [res] = ok(owner.get(url(f"/cycle-cases/{first['id']}/results")))["items"]
        assert (res["status"], res["skip_reason"], res["build"]) == ("skip", "env", "2.0.1")
        assert [s["status"] for s in res["steps"]] == ["ignore", "cancel"]
        assert [d["url"] for d in res["defects"]] == ["https://issues.example.com/OPS-3"]

    @test()
    def test_skip_reason_other_with_no_comment_is_refused_raw(self, suite_parameter):
        owner = self.live.owner
        cc = world(owner)["ccs"][0]["id"]
        body = {"status": "skip", "skip_reason": "other"}
        out = self.js(
            f"""return await h.fail(a.actions.submit("{cc}", {json.dumps(body)}, ctx));""", {"product": "PAY"}
        )
        direct = owner.post(url(f"/cycle-cases/{cc}/results"), json=body)
        assert direct.status_code == 422 and out["status"] == 422
        assert out["raw"] == as_sent(direct)

    @test()
    def test_a_result_on_a_closed_cycle_is_refused_raw(self, suite_parameter):
        owner = self.live.owner
        w = world(owner)
        cc = w["ccs"][0]["id"]
        ok(owner.post(url(f"/cycles/{w['cycle']['id']}/close")))
        code = f"""return await h.fail(a.actions.submit("{cc}", {{ status: "success" }}, ctx));"""
        out = self.js(code, {"product": "PAY"})
        direct = owner.post(url(f"/cycle-cases/{cc}/results"), json={"status": "success"})
        assert out["name"] == "ApiError" and out["status"] == direct.status_code >= 400
        assert out["raw"] == as_sent(direct)
