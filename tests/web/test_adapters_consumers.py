"""Web adapter for Consumers (machines), run in node against a live server: the list and its
server-side status filter and name search, the pairing steps (preview, approve, deny), one machine's
detail with its jobs, roster and heartbeats, the writes (rename, pause, resume, revoke), and raw
errors."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_product, ok
from tests.test_consumers import ROSTER, FakeConsumer, approve
from tests.test_jobs import create, make_world, next_job, report
from tests.web.live import LiveServer, as_sent, body_of, run_js

ORG = "/api/v1/orgs/acme"
URL = "/app?view=consumers"


@Suite(parameters=support.DATABASES)
class WebConsumersAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def machine(self, name, product_id, beat=True):
        """A paired, claimed machine; it heartbeats unless beat is False."""
        fake = FakeConsumer(self.live.env)
        fake.start()
        fake.consumer = ok(approve(self.live.owner, fake.pairing["user_code"], name, [product_id]), 201)
        fake.claim()
        if beat:
            ok(fake.heartbeat())
        return fake

    def js(self, body):
        return run_js(
            self.live,
            f"""await h.signIn();
            const ctx = await h.ctx({{}});
            const c = await h.adapter("consumers");
            {body}""",
            URL,
        )

    def load(self, params):
        return self.js(f"return await c.load({json.dumps(params)}, ctx);")

    @test()
    def test_no_machines_is_the_empty_state(self, suite_parameter):
        make_product(self.live.owner)
        out = self.load({})
        assert out["state"] == "empty"
        assert out["data"]["machines"] == [] and out["data"]["counts"]["all"] == 0

    @test()
    def test_list_status_filter_and_search_are_the_servers(self, suite_parameter):
        pay = make_product(self.live.owner)
        self.machine("QA lab Mac mini", pay["id"])
        self.machine("Perf box", pay["id"], beat=False)
        out = self.load({})
        assert out["state"] == "list"
        assert out["data"]["counts"] == {"all": 2, "online": 1, "busy": 0, "offline": 1}
        cards = {m["name"]: m for m in out["data"]["machines"]}
        mac = cards["QA lab Mac mini"]
        assert (mac["status"], mac["os"], mac["tj"], mac["python"]) == ("online", "Linux", "1.9.0", "3.13.1")
        assert (mac["products"], mac["projects"], mac["paused"]) == (["PAY"], 0, False)
        assert mac["heartbeat"].endswith(" ago") and cards["Perf box"]["heartbeat"] == "never"
        online = self.js(
            """const s = await c.load({ status: "online" }, ctx);
            return { s, asked: h.calls.map((x) => x.path).filter((p) => p.includes("/consumers?")) };"""
        )
        assert online["s"]["state"] == "filter-online"
        assert [m["name"] for m in online["s"]["data"]["machines"]] == ["QA lab Mac mini"]
        assert "/api/v1/orgs/acme/consumers?status=online&limit=200" in online["asked"]
        search = self.load({"q": "lab"})
        assert search["state"] == "search"
        assert [m["name"] for m in search["data"]["machines"]] == ["QA lab Mac mini"]
        assert self.load({"q": "jenkins"})["state"] == "search-empty"

    @test()
    def test_pairing_previews_the_request_and_approve_pairs_it(self, suite_parameter):
        pay = make_product(self.live.owner)
        fake = FakeConsumer(self.live.env)
        code = fake.start({"os": "macOS 15", "tj_version": "0.8.9", "python": "3.11", "projects": ["web"]})[
            "user_code"
        ]
        assert self.load({"ui": "pair"})["state"] == "pair"
        out = self.load({"code": code})
        assert out["state"] == "pair-approve"
        p = out["data"]["pair"]
        assert (p["code"], p["os"], p["tj"], p["python"], p["projects"]) == (
            code.replace("-", ""),
            "macOS 15",
            "0.8.9",
            "3.11",
            ["web"],
        )
        assert p["expiresIn"].endswith(" s") and p["name"] == ""
        assert self.load({"code": code, "ui": "pair-noname"})["state"] == "pair-noname"
        assert self.load({"code": code, "ui": "pair"})["data"]["pair"]["typed"] == code.replace("-", "")
        made = self.js(
            f"""const m = await c.actions.approve({{ code: "{code}", name: "QA lab", products: ["PAY"],
              acceptNow: false }}, ctx);
            return {{ m, after: await c.load({{ paired: m.id }}, ctx) }};"""
        )
        assert made["m"]["name"] == "QA lab" and made["m"]["product_ids"] == [pay["id"]]
        stored = ok(self.live.owner.get(f"{ORG}/consumers/{made['m']['id']}"))
        assert stored["name"] == "QA lab" and stored["paused_at"] is not None
        assert made["after"]["state"] == "paired"
        assert made["after"]["data"]["paired"]["name"] == "QA lab"
        assert made["after"]["data"]["paired"]["products"] == ["PAY"]

    @test()
    def test_deny_refuses_the_request(self, suite_parameter):
        make_product(self.live.owner)
        fake = FakeConsumer(self.live.env)
        code = fake.start()["user_code"]
        assert self.js(f'return await c.actions.deny("{code}", ctx);') is None
        poll = fake.poll()
        assert poll.status_code == 403 and poll.json()["error"] == "access_denied"
        again = self.js(f'return h.fail(c.actions.deny("{code}", ctx));')
        raw = as_sent(self.live.owner.post(f"{ORG}/pair/deny", json={"user_code": code}))
        assert again == {"name": "ApiError", "status": 409, "raw": raw}

    @test()
    def test_detail_maps_jobs_roster_and_heartbeats(self, suite_parameter):
        owner = self.live.owner
        world = make_world(self.live.env, owner, None)
        a = world["a"]
        cid = a.consumer["id"]
        ok(create(owner, world, a), 201)
        rejected = ok(next_job(a))
        ok(report(a, rejected["id"], "rejected", reason="no browser"))
        ok(create(owner, world, a), 201)
        out = self.load({"id": cid})
        assert out["state"] == "job-rejected"
        m = out["data"]["machine"]
        assert (m["name"], m["status"], m["jobsToday"], m["rejectedToday"]) == ("box-a", "online", 2, 1)
        assert (m["testsFound"], m["testsLinked"], m["products"]) == (2, 2, ["PAY"])
        assert m["projects"] == [{"name": "web", "products": []}]
        assert [(j["state"], j["name"], j["project"]) for j in m["jobs"]] == [
            ("queued", "Nightly", "web"),
            ("rejected", "Nightly", "web"),
        ]
        assert m["jobs"][1]["reason"] == "no browser" and m["rejectError"] == "no browser"
        assert [t["ref"] for t in m["tests"]] == [r["id"] for r in ROSTER]
        assert all(t["caseKey"] and t["caseKey"].startswith("PAY-") for t in m["tests"])
        assert len(m["hb"]["beats"]) == 24 and sum(m["hb"]["beats"]) >= 1 and sum(m["hb"]["jobs"]) == 2
        assert m["hb"]["expected"] is None
        assert self.load({"id": cid, "ui": "rename"})["state"] == "rename"
        idle = self.load({"id": world["b"].consumer["id"]})
        assert idle["state"] == "detail" and idle["data"]["machine"]["jobs"] == []

    @test()
    def test_a_silent_machine_is_the_offline_state(self, suite_parameter):
        pay = make_product(self.live.owner)
        fake = self.machine("Perf box", pay["id"], beat=False)
        out = self.load({"id": fake.consumer["id"]})
        assert out["state"] == "offline"
        assert out["data"]["machine"]["silentFor"] == "" and out["data"]["machine"]["lastHeartbeat"] == ""

    @test()
    def test_rename_pause_resume_and_revoke_reach_the_server(self, suite_parameter):
        pay = make_product(self.live.owner)
        cid = self.machine("box", pay["id"]).consumer["id"]
        out = self.js(
            f"""const renamed = await c.actions.rename("{cid}", "QA lab Mac mini", ctx);
            const paused = await c.actions.pause("{cid}", ctx);
            const shown = (await c.load({{ id: "{cid}" }}, ctx)).data.machine.paused;
            const resumed = await c.actions.resume("{cid}", ctx);
            return {{ renamed, paused, shown, resumed }};"""
        )
        assert out["renamed"]["name"] == "QA lab Mac mini"
        assert out["paused"]["paused_at"] is not None and out["shown"] is True
        assert out["resumed"]["paused_at"] is None
        stored = ok(self.live.owner.get(f"{ORG}/consumers/{cid}"))
        assert stored["name"] == "QA lab Mac mini" and stored["paused_at"] is None
        assert self.js(f'return await c.actions.revoke("{cid}", ctx);') is None
        assert ok(self.live.owner.get(f"{ORG}/consumers/{cid}"))["status"] == "revoked"
        assert self.load({})["state"] == "empty"

    @test()
    def test_duplicate_name_is_the_raw_409(self, suite_parameter):
        pay = make_product(self.live.owner)
        self.machine("box-a", pay["id"])
        cid = self.machine("box-b", pay["id"]).consumer["id"]
        out = self.js(f'return h.fail(c.actions.rename("{cid}", "box-a", ctx));')
        raw = as_sent(self.live.owner.patch(f"{ORG}/consumers/{cid}", json={"name": "box-a"}))
        assert body_of(raw)["status"] == 409
        assert out == {"name": "ApiError", "status": 409, "raw": raw}

    @test()
    def test_unknown_pairing_code_is_the_raw_404(self, suite_parameter):
        make_product(self.live.owner)
        out = self.js('return h.fail(c.load({ code: "BBBBCCCC" }, ctx));')
        assert out["status"] == 404
        assert out["raw"] == as_sent(self.live.owner.get(f"{ORG}/pair/BBBBCCCC"))
