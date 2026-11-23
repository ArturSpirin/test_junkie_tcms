"""Web adapter for Start a cycle, run in node against a live server: the wizard's steps (plan or features, the
runner counts from the preview, the machines with a busy one's queue ETA, none online), starting a cycle in
each mode (with split, retries and queuing on an offline machine) read back from the server, the live cycle's
states (queued, live, mixed, done, a stalled machine, stopped), the writes (reassign, cancel, stop), and a raw
error."""

import json
from datetime import timedelta

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_plan, ok, seed, url
from tests.execution_seed import activate
from tests.support import add_member
from tests.test_consumers import FakeConsumer, approve
from tests.test_jobs import REF_BAD, REF_OK, create, job_list, make_clock, make_world, next_job, report
from tests.web.live import LiveServer, as_sent, run_js

URL = "/app?view=start"


@Suite(parameters=support.DATABASES)
class WebStartAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def world(self):
        """PAY › Checkout › Card with 4 cases (2 automated that box-a and box-b list, 1 manual, 1
        automated that no machine lists), release 1.0 listing Card, the active plan Smoke (Card), and a
        tester."""
        self.clock = make_clock(self.live.env)
        w = make_world(self.live.env, self.live.owner, self.clock)
        s = ok(self.live.owner.get(url(f"/products/{w['product']}/plans")))["items"][0]
        w["plan"] = activate(self.live.owner, s["id"])
        w["tester"] = add_member(self.live.owner, "lee@example.com", "tester")
        return w

    def js(self, body):
        return run_js(
            self.live,
            f"""await h.signIn();
            const ctx = await h.ctx({{ product: "PAY" }});
            const a = await h.adapter("start");
            {body}""",
            URL,
        )

    def load(self, params):
        return self.js(f"return await a.load({json.dumps({'product': 'PAY', **params})}, ctx);")

    def start_cycle(self, form):
        return self.js(f"return await a.actions.start({json.dumps(form)}, ctx, 'PAY');")

    @test()
    def test_wizard_picks_the_active_plan_and_counts_each_runner(self, suite_parameter):
        w = self.world()
        draft = make_plan(self.live.owner, w["product"], "Wallet limits")
        out = self.load({})
        assert out["state"] == "scope"
        d = out["data"]
        assert d["query"]["plan"] == w["plan"]["id"] and d["query"]["features"] is None
        assert d["plan"] == {"id": w["plan"]["id"], "name": "Smoke", "cases": 4, "automated": 2, "manual": 2}
        plans = {p["id"]: p for p in d["plans"]}
        assert plans[w["plan"]["id"]]["meta"] == "1 feature · 4 cases" and plans[w["plan"]["id"]]["on"]
        assert plans[draft["id"]]["cantRun"] and plans[draft["id"]]["meta"] == "draft"
        assert [(f["path"], f["on"]) for f in d["features"]] == [
            ("Checkout", False),
            ("Checkout › Card", True),
        ]
        assert [(m["name"], m["status"], m["on"]) for m in d["machines"]] == [
            ("box-a", "online", True),
            ("box-b", "online", True),
        ]
        assert d["machines"][0]["meta"] == "Linux · tj 1.9.0 · idle"
        assert d["tester"] == w["tester"]["actor_id"]
        assert {t["role"] for t in d["testers"]} == {"owner", "tester"}
        assert (d["version"], d["order"], d["cycleName"]) == ("1.0", "feature", "Smoke")
        for ui in ("mode", "mode-manual", "mode-mixed", "manual-ready", "auto-pick", "mixed-pick"):
            assert self.load({"ui": ui})["state"] == ui
        one = self.load({"ui": "auto-pick", "machines": w["a"].consumer["id"]})["data"]["machines"]
        assert [m["on"] for m in one] == [True, False]

    @test()
    def test_scope_by_features_previews_the_features(self, suite_parameter):
        w = self.world()
        out = self.load({"ui": "scope-features"})
        assert out["state"] == "scope-features"
        d = out["data"]
        card = [f["id"] for f in d["features"] if f["on"]]
        assert d["query"]["features"] == ",".join(card) and d["query"]["plan"] is None
        assert (d["plan"]["id"], d["plan"]["name"], d["plan"]["cases"]) == (None, "1 feature", 4)
        named = self.load({"features": card[0], "env": "staging"})
        assert named["data"]["cycleName"] == "1 feature · staging"
        assert w["plan"]["status"] == "active"

    @test()
    def test_a_busy_machine_says_when_its_queue_frees(self, suite_parameter):
        w = self.world()
        eta = (self.clock.now + timedelta(minutes=30)).isoformat()
        ok(create(self.live.owner, w, w["a"], mode="automated", eta=eta), 201)
        ok(next_job(w["a"]))
        m = {x["name"]: x for x in self.load({"ui": "auto-pick"})["data"]["machines"]}
        assert m["box-a"]["status"] == "busy" and m["box-a"]["on"]
        assert m["box-a"]["meta"].startswith("Linux · tj 1.9.0 · queues after its current job (about ")

    @test()
    def test_no_machine_online_is_auto_none(self, suite_parameter):
        s = seed(self.live.owner)
        activate(self.live.owner, s["plan"]["id"])
        fake = FakeConsumer(self.live.env)
        fake.start()
        fake.consumer = ok(
            approve(self.live.owner, fake.pairing["user_code"], "box-a", [s["product"]["id"]]), 201
        )
        fake.claim()
        out = self.load({"ui": "auto-pick"})
        assert out["state"] == "auto-none"
        assert [(m["status"], m["meta"], m["on"]) for m in out["data"]["machines"]] == [
            ("offline", "No heartbeat yet", False)
        ]
        assert out["data"]["heartbeatWindow"] == ""

    @test()
    def test_start_manual_sends_tester_order_and_environment(self, suite_parameter):
        w = self.world()
        c = self.start_cycle(
            {
                "plan": w["plan"]["id"],
                "name": "Smoke · staging",
                "environment": "staging",
                "mode": "manual",
                "tester": w["tester"]["actor_id"],
                "order": "priority",
            }
        )
        back = ok(self.live.owner.get(url(f"/cycles/{c['id']}")))
        assert (back["plan_id"], back["name"], back["environment"]) == (
            w["plan"]["id"],
            "Smoke · staging",
            "staging",
        )
        assert (back["mode"], back["order"], back["default_assignee_actor_id"]) == (
            "manual",
            "priority",
            w["tester"]["actor_id"],
        )
        assert job_list(self.live.owner, c["id"]) == []

    @test()
    def test_automated_run_goes_queued_live_done(self, suite_parameter):
        w = self.world()
        ids = [w["a"].consumer["id"], w["b"].consumer["id"]]
        c = self.start_cycle(
            {
                "plan": w["plan"]["id"],
                "name": "Smoke",
                "environment": "",
                "mode": "auto",
                "tester": "none",
                "machines": ids,
            }
        )
        back = ok(self.live.owner.get(url(f"/cycles/{c['id']}")))
        assert (back["mode"], back["order"], back["default_assignee_actor_id"]) == (
            "automated",
            "source",
            None,
        )
        assert sorted(j["consumer_id"] for j in job_list(self.live.owner, c["id"])) == sorted(ids)
        queued = self.load({"id": c["id"]})
        assert queued["state"] == "queued"
        assert [j["status"] for j in queued["data"]["cycle"]["jobs"]] == ["queued", "queued"]
        ja = ok(next_job(w["a"]))
        running = self.load({"id": c["id"]})
        assert running["state"] == "live"
        assert (running["data"]["cycle"]["total"], running["data"]["cycle"]["done"]) == (2, 0)
        ok(report(w["a"], ja["id"], "done", (REF_OK, "success")))
        jb = ok(next_job(w["b"]))
        ok(report(w["b"], jb["id"], "done", (REF_BAD, "fail")))
        done = self.load({"id": c["id"]})
        assert done["state"] == "done"
        cy = done["data"]["cycle"]
        assert (cy["done"], cy["passed"], cy["failed"], cy["passedPct"]) == (2, 1, 1, 50)
        assert cy["failedKeys"] == [w["cases"]["bad"]["key"]]
        assert cy["manual"]["count"] == 2 and cy["finished"]

    @test()
    def test_stop_cancels_the_queued_jobs_and_the_live_cycle_says_who_stopped_it(self, suite_parameter):
        w = self.world()
        ids = [w["a"].consumer["id"], w["b"].consumer["id"]]
        c = self.start_cycle({"plan": w["plan"]["id"], "name": "Smoke", "mode": "auto", "machines": ids})
        assert self.load({"id": c["id"]})["data"]["cycle"]["stopped"] is False
        self.js(f"return await a.actions.stop({json.dumps(c['id'])}, ctx);")
        back = ok(self.live.owner.get(url(f"/cycles/{c['id']}")))
        assert back["stopped_at"] and back["status"] == "open"
        assert {j["status"] for j in job_list(self.live.owner, c["id"])} == {"cancelled"}
        cy = self.load({"id": c["id"]})["data"]["cycle"]
        assert (cy["stopped"], cy["stoppedBy"]) == (True, "Olive Owner")

    @test()
    def test_mixed_run_assigns_the_manual_cases(self, suite_parameter):
        w = self.world()
        c = self.start_cycle(
            {
                "plan": w["plan"]["id"],
                "name": "Smoke",
                "mode": "mixed",
                "tester": w["tester"]["actor_id"],
                "machines": [w["a"].consumer["id"]],
            }
        )
        back = ok(self.live.owner.get(url(f"/cycles/{c['id']}")))
        assert (back["mode"], back["default_assignee_actor_id"]) == ("both", w["tester"]["actor_id"])
        ok(next_job(w["a"]))
        out = self.load({"id": c["id"]})
        assert out["state"] == "mixed"
        assert out["data"]["cycle"]["manualTester"] == w["tester"]["actor_id"]
        assert out["data"]["cycle"]["manual"]["count"] == 2

    def stalled(self):
        """An automated run on box-a and box-b; then box-a stops beating and box-b beats on."""
        w = self.world()
        c = ok(create(self.live.owner, w, w["a"], w["b"], mode="automated", name="Smoke"), 201)
        self.clock.tick(120)
        ok(w["b"].heartbeat())
        return w, c

    @test()
    def test_a_stalled_machine_is_offline_mid_and_reassign_moves_its_job(self, suite_parameter):
        w, c = self.stalled()
        out = self.load({"id": c["id"]})
        assert out["state"] == "offline-mid"
        s = out["data"]["cycle"]["stalled"]
        assert (s["machine"], s["waiting"], s["reassignTo"], s["reassignId"]) == (
            "box-a",
            1,
            "box-b",
            w["b"].consumer["id"],
        )
        assert self.load({"id": c["id"], "ui": "cancel-cases"})["state"] == "cancel-cases"
        self.js(
            f"return await a.actions.reassign({json.dumps(s['jobId'])}, {json.dumps(s['reassignId'])}, ctx);"
        )
        moved = [j for j in job_list(self.live.owner, c["id"]) if j["id"] == s["jobId"]][0]
        assert moved["consumer_id"] == w["b"].consumer["id"]
        after = self.load({"id": c["id"], "moved": "1", "to": "box-b", "ui": "reassigned"})
        assert after["state"] == "reassigned" and after["data"]["moved"] == {"count": 1, "to": "box-b"}

    @test()
    def test_cancel_cancels_the_stalled_job(self, suite_parameter):
        w, c = self.stalled()
        s = self.load({"id": c["id"]})["data"]["cycle"]["stalled"]
        self.js(f"return await a.actions.cancel({json.dumps(s['jobId'])}, ctx);")
        gone = [j for j in job_list(self.live.owner, c["id"]) if j["id"] == s["jobId"]][0]
        assert gone["status"] == "cancelled"

    @test()
    def test_an_offline_machine_is_the_raw_409(self, suite_parameter):
        w, _ = self.stalled()
        body = {
            "plan_id": w["plan"]["id"],
            "name": "Smoke",
            "environment": None,
            "mode": "automated",
            "consumer_ids": [w["a"].consumer["id"]],
            "default_assignee_actor_id": None,
            "order": "source",
        }
        out = self.js(
            f"""return await h.fail(a.actions.start({{ plan: {json.dumps(w["plan"]["id"])}, name: "Smoke",
              mode: "auto", tester: "none", machines: [{json.dumps(w["a"].consumer["id"])}] }},
              ctx, "PAY"));"""
        )
        direct = self.live.owner.post(url("/products/PAY/cycles"), json=body)
        assert direct.status_code == 409 and out["status"] == 409
        assert out["raw"] == as_sent(direct)

    @test()
    def test_split_retries_and_queue_when_offline_reach_the_server(self, suite_parameter):
        w, _ = self.stalled()
        c = self.start_cycle(
            {
                "plan": w["plan"]["id"],
                "name": "Smoke",
                "mode": "auto",
                "machines": [w["a"].consumer["id"]],
                "split": "by_feature",
                "retries": "2",
                "offline": True,
            }
        )
        back = ok(self.live.owner.get(url(f"/cycles/{c['id']}")))
        assert (back["split"], back["retries"], back["queued_offline"]) == ("by_feature", 2, 1)
        manual = self.start_cycle(
            {
                "plan": w["plan"]["id"],
                "name": "By hand",
                "mode": "manual",
                "split": "first_free",
                "retries": 2,
            }
        )
        assert (manual["split"], manual["retries"]) == ("even", 0)
