"""Web adapter for a case's version history, run in node against a live server: the state each URL gives, the
history rows and their provenance, the compare of two picked versions, the cycles that pin a version, the
restore (read back from the server) and a raw error."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import ok, seed, url
from tests.execution_seed import STEPS, edit_steps, make_case, make_cycle
from tests.web.live import LiveServer, as_sent, body_of, run_js


@Suite(parameters=support.DATABASES)
class WebVersionsAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def seed(self):
        """PAY's catalog seed and one case with three versions: v1 created, v2 a new title, v3 new steps."""
        owner = self.live.owner
        s = seed(owner)
        case = make_case(owner, s["product"]["id"], s["child"]["id"], "Pay by card", steps=STEPS)
        ok(
            owner.patch(
                url(f"/cases/{case['key']}"),
                json={"title": "Pay with a saved card", "change_note": "Clearer title"},
                headers={"If-Match": '"1"'},
            )
        )
        edit_steps(owner, case, 2)
        return {**s, "case": case}

    def load(self, params):
        """The adapter's { state, data } for params, signed in as the acme owner, with the shell's context."""
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps({"product": "PAY", **params})};
            const ctx = await h.ctx(params);
            return await (await h.adapter("versions")).load(params, ctx);""",
            "/app?view=versions&product=PAY",
        )

    @test()
    def test_default_lists_the_versions_and_compares_the_latest_two(self, suite_parameter):
        s = self.seed()
        out = self.load({"id": s["case"]["key"]})
        assert out["state"] == "default"
        d = out["data"]
        assert d["case"]["key"] == s["case"]["key"] and d["case"]["title"] == "Pay with a saved card"
        c = d["case"]
        assert (c["product"], c["feature"], c["version"]) == ("PAY product", "Card", 3)
        assert d["pick"] == {"a": 2, "b": 3}
        api = ok(self.live.owner.get(url(f"/cases/{s['case']['id']}/versions")))["items"]
        assert [v["n"] for v in d["versions"]] == [3, 2, 1]
        assert [v["note"] for v in d["versions"]][1] == "Clearer title"
        for row, v in zip(d["versions"], api, strict=True):
            want = ("person", v["created_by_actor_id"], v["via"] or "")
            assert (row["kind"], row["who"], row["via"]) == want
            assert row["forWho"] == ""
        # v2 -> v3: the first step reworded, the second dropped, a new one added
        labels = [f["label"] for f in d["diff"]["fields"]]
        first, second = (st["id"] for st in s["case"]["steps"])
        assert f"Step {first} · action" in labels and f"Step {first} · expected" in labels
        assert f"Step {second} · removed" in labels
        assert any(x.endswith(" · added") for x in labels)
        action = next(f for f in d["diff"]["fields"] if f["label"] == f"Step {first} · action")
        assert action["from"] == [{"text": "Open the cart"}]
        assert action["to"] == [{"text": "Open the "}, {"del": "cart"}, {"ins": "basket"}]
        assert d["diff"]["note"] == {"from": "Clearer title", "to": ""}
        assert d["diff"]["unchanged"].startswith("Title, ")
        assert d["used"] == [] and d["draft"] == {"note": "Restored v2"}

    @test()
    def test_two_picked_versions_are_the_compare(self, suite_parameter):
        s = self.seed()
        out = self.load({"id": s["case"]["id"], "a": "1", "b": "3"})
        assert out["state"] == "compare"
        assert out["data"]["pick"] == {"a": 1, "b": 3}
        title = next(f for f in out["data"]["diff"]["fields"] if f["label"] == "Title")
        assert title["from"] == [{"text": "Pay by card"}]
        assert "".join(x.get("text", "") + x.get("ins", "") for x in title["to"]) == "Pay with a saved card"
        # the latest two picked explicitly are the default view
        assert self.load({"id": s["case"]["id"], "a": "2", "b": "3"})["state"] == "default"

    @test()
    def test_used_in_cycles_maps_each_cycle_its_release_and_pin(self, suite_parameter):
        s = self.seed()
        cycle = make_cycle(
            self.live.owner,
            s["product"]["id"],
            name="Checkout · staging",
            case_ids=[s["case"]["id"]],
            release_id=s["release"]["id"],
        )
        out = self.load({"id": s["case"]["key"], "ui": "used-in-cycles"})
        assert out["state"] == "used-in-cycles"
        assert out["data"]["used"] == [
            {
                "id": cycle["id"],
                "cycle": "Checkout · staging",
                "release": s["release"]["version"],
                "pinned": 3,
                "result": "untested",
                "note": "current",
                "open": True,
            }
        ]
        assert self.load({"id": s["case"]["key"], "ui": "restore-confirm"})["state"] == "restore-confirm"

    @test()
    def test_restore_makes_a_new_version_from_the_old_one(self, suite_parameter):
        s = self.seed()
        out = run_js(
            self.live,
            f"""await h.signIn();
            const ctx = await h.ctx({{ product: "PAY" }});
            const v = await h.adapter("versions");
            const c = await v.actions.restore({json.dumps(s["case"]["id"])}, 1, "Back to v1", 3, ctx);
            const p = {{ id: c.key, a: "1", b: String(c.current_version), ui: "restored" }};
            const after = await v.load(p, ctx);
            return {{ c, after }};""",
            "/app?view=versions&product=PAY",
        )
        assert out["c"]["current_version"] == 4
        back = ok(self.live.owner.get(url(f"/cases/{s['case']['id']}/versions/4")))
        assert (back["title"], back["change_note"]) == ("Pay by card", "Back to v1")
        assert [st["id"] for st in back["steps"]] == [st["id"] for st in s["case"]["steps"]]
        assert out["after"]["state"] == "restored"
        assert out["after"]["data"]["pick"] == {"a": 1, "b": 4}
        assert out["after"]["data"]["versions"][0]["note"] == "Back to v1"
        assert out["after"]["data"]["diff"]["fields"] == []

    @test()
    def test_restore_on_a_stale_version_is_the_raw_409(self, suite_parameter):
        s = self.seed()
        out = run_js(
            self.live,
            f"""await h.signIn();
            const ctx = await h.ctx({{ product: "PAY" }});
            const v = await h.adapter("versions");
            return h.fail(v.actions.restore({json.dumps(s["case"]["id"])}, 1, "", 2, ctx));""",
            "/app?view=versions&product=PAY",
        )
        raw = as_sent(
            self.live.owner.post(
                url(f"/cases/{s['case']['id']}/restore"),
                json={"version": 1, "change_note": None},
                headers={"If-Match": "2"},
            )
        )
        assert body_of(raw)["status"] == 409
        assert out == {"name": "ApiError", "status": 409, "raw": raw}
