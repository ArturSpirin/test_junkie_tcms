"""Web adapter for Test plans, run in node against a live server: the list with its server-side name
search and the version and status filters, one plan's detail with its per-entry resolution counts,
the writes (create, edit entries, change status, make a cycle) read back from the server, and a raw
error."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_feature, make_plan, make_product, make_release, ok, url
from tests.execution_seed import activate, make_case, make_cycle
from tests.web.live import LiveServer, as_sent, run_js

URL = "/app?view=plans"


@Suite(parameters=support.DATABASES)
class WebPlansAdapter:
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
        """PAY with Checkout › Card (2 cases, one tagged visa) and Checkout › Wallets (1 case, deprecated one
        more), release 2.14.0 listing Card, and the plans Checkout regression (active: Card, a visa query and
        one Wallets case) and Wallet limits (draft, any version)."""
        owner = self.live.owner
        p = make_product(owner, "PAY", name="Payments")
        checkout = make_feature(owner, p["id"], "Checkout")
        card = make_feature(owner, p["id"], "Card", parent_id=checkout["id"])
        wallets = make_feature(owner, p["id"], "Wallets", parent_id=checkout["id"])
        c1 = make_case(owner, p["id"], card["id"], "Pay with a saved Visa card", tags=["visa"])
        c2 = make_case(owner, p["id"], card["id"], "Decline on insufficient funds")
        w1 = make_case(owner, p["id"], wallets["id"], "Apple Pay sheet opens")
        make_case(owner, p["id"], wallets["id"], "Old wallet flow", status="deprecated")
        rel = make_release(owner, p["id"], "2.14.0", status="in_progress")
        ok(owner.put(url(f"/releases/{rel['id']}/features"), json={"feature_ids": [card["id"]]}))
        reg = make_plan(owner, p["id"], "Checkout regression", release_id=rel["id"])
        entries = [{"feature_id": card["id"]}, {"query": {"tags": ["visa"]}}, {"case_id": w1["key"]}]
        reg = ok(owner.post(url(f"/plans/{reg['id']}/entries"), json={"entries": entries}))
        activate(owner, reg["id"])
        draft = make_plan(owner, p["id"], "Wallet limits")
        return {
            "product": p,
            "card": card,
            "wallets": wallets,
            "cases": [c1, c2, w1],
            "release": rel,
            "reg": reg,
            "draft": draft,
        }

    def js(self, body, params=None):
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps(params or {"product": "PAY"})};
            const ctx = await h.ctx(params);
            const a = await h.adapter("plans");
            {body}""",
            URL,
        )

    def load(self, params):
        params = {"product": "PAY", **params}
        return self.js("return await a.load(params, ctx);", params)

    @test()
    def test_no_plans_is_the_empty_state(self, suite_parameter):
        make_product(self.live.owner, "PAY")
        out = self.load({})
        assert out["state"] == "empty"
        assert out["data"]["plans"] == [] and out["data"]["total"] == 0
        assert self.load({"ui": "new"})["state"] == "new"

    @test()
    def test_list_maps_each_plan_with_its_counts_and_last_cycle(self, suite_parameter):
        w = self.world()
        old = make_plan(self.live.owner, w["product"]["id"], "Payouts sign-off")
        activate(self.live.owner, old["id"])
        ok(self.live.owner.patch(url(f"/plans/{old['id']}"), json={"status": "archived"}))
        cy = make_cycle(self.live.owner, w["product"]["id"], plan_id=w["reg"]["id"], name="Reg · staging")
        out = self.load({})
        assert out["state"] == "list"
        assert out["data"]["total"] == 3 and out["data"]["statusFilter"] == ["active", "draft"]
        rows = {p["name"]: p for p in out["data"]["plans"]}
        assert sorted(rows) == ["Checkout regression", "Wallet limits"]
        reg = rows["Checkout regression"]
        # Card's 2 cases, the visa query adds nothing new, the Wallets case adds 1 (F3 new_cases)
        assert (reg["status"], reg["version"], reg["cases"]) == ("active", "2.14.0", "3 cases")
        assert reg["scope"] == "1 feature · 1 query · 1 case"
        assert reg["results"] == {"untested": 3} and cy["counts"]["untested"] == 3
        assert rows["Wallet limits"]["version"] == "any version" and rows["Wallet limits"]["results"] == {}
        arch = self.load({"status": "archived"})
        assert [p["name"] for p in arch["data"]["plans"]] == ["Payouts sign-off"]
        ver = self.load({"version": "2.14.0"})
        assert [p["name"] for p in ver["data"]["plans"]] == ["Checkout regression"]

    @test()
    def test_search_is_the_servers_q(self, suite_parameter):
        self.world()
        out = self.js(
            """const s = await a.load({ ...params, q: "wallet" }, ctx);
            return { s, asked: h.calls.map((c) => c.path).filter((p) => p.includes("/plans?")) };"""
        )
        assert out["s"]["state"] == "search"
        assert [p["name"] for p in out["s"]["data"]["plans"]] == ["Wallet limits"]
        assert any("q=wallet" in p for p in out["asked"])
        none = self.load({"q": "invoice"})
        assert none["state"] == "search-empty" and none["data"]["plans"] == []
        assert self.load({"ui": "search-cleared"})["state"] == "search-cleared"

    @test()
    def test_detail_maps_entries_and_resolution_counts(self, suite_parameter):
        w = self.world()
        out = self.load({"id": w["reg"]["id"]})
        assert out["state"] == "detail"
        p = out["data"]["detail"]
        assert (p["name"], p["status"], p["version"], p["versionStatus"]) == (
            "Checkout regression",
            "active",
            "2.14.0",
            "in_progress",
        )
        assert [(e["kind"], e["label"]) for e in p["entries"]] == [
            ("feature", "Checkout › Card"),
            ("query", "tags: visa"),
            ("case", f"{w['cases'][2]['key']} · Apple Pay sheet opens"),
        ]
        assert p["entries"][0]["meta"].endswith("now 2")
        assert p["entries"][1]["meta"] == "matches 1 · 1 already in an entry above"
        assert p["resolve"]["features"] == 1 and p["resolve"]["featureCases"] == 2
        assert (p["resolve"]["queryNew"], p["resolve"]["cases"], p["resolve"]["pinned"]) == (0, 1, 3)
        assert p["resolve"]["example"]["key"] == w["cases"][0]["key"]
        assert p["cycles"] == [] and p["latest"] is None
        nc = out["data"]["newCycle"]
        assert [r["count"] for r in nc["resolved"]] == [2, 0, 1]
        assert nc["deprecated"] == 0 and nc["env"] == "new"
        assert [f["path"] for f in out["data"]["features"]] == [
            "Checkout",
            "Checkout › Card",
            "Checkout › Wallets",
        ]
        assert self.load({"id": w["reg"]["id"], "ui": "edit"})["state"] == "edit"
        assert self.load({"id": w["reg"]["id"], "ui": "create-cycle"})["state"] == "create-cycle"
        draft = self.load({"id": w["draft"]["id"]})
        assert draft["data"]["newCycle"]["deprecated"] is None

    @test()
    def test_create_makes_the_plan_with_the_versions_features_and_entries(self, suite_parameter):
        w = self.world()
        out = self.js(
            f"""const form = {{ name: "Card smoke", version: "{w["release"]["id"]}", allFeatures: true,
              entries: [{{ case_id: "{w["cases"][2]["key"]}" }}] }};
            return await a.actions.create(form, ctx, "PAY");"""
        )
        back = ok(self.live.owner.get(url(f"/plans/{out['id']}")))
        assert (back["name"], back["release_id"]) == ("Card smoke", w["release"]["id"])
        assert [(e["feature_id"], e["case_id"]) for e in back["entries"]] == [
            (w["card"]["id"], None),
            (None, w["cases"][2]["id"]),
        ]

    @test()
    def test_save_entries_removes_then_adds(self, suite_parameter):
        w = self.world()
        gone = w["reg"]["entries"][1]["id"]
        self.js(
            f"""return await a.actions.saveEntries("{w["reg"]["id"]}",
              {{ remove: ["{gone}"], add: [{{ feature_id: "{w["wallets"]["id"]}" }}] }}, ctx);"""
        )
        back = ok(self.live.owner.get(url(f"/plans/{w['reg']['id']}")))
        assert gone not in [e["id"] for e in back["entries"]]
        assert back["entries"][-1]["feature_id"] == w["wallets"]["id"] and len(back["entries"]) == 3

    @test()
    def test_update_changes_the_status(self, suite_parameter):
        w = self.world()
        self.js(f"""return await a.actions.update("{w["draft"]["id"]}", {{ status: "active" }}, ctx);""")
        assert ok(self.live.owner.get(url(f"/plans/{w['draft']['id']}")))["status"] == "active"

    @test()
    def test_create_cycle_then_the_cycle_created_state(self, suite_parameter):
        w = self.world()
        out = self.js(
            f"""const c = await a.actions.createCycle("{w["reg"]["id"]}",
              {{ name: "Reg · staging", environment: "staging" }}, ctx, "PAY");
            return {{ c, after: await a.load({{ ...params, id: "{w["reg"]["id"]}", cycle: c.id }}, ctx) }};"""
        )
        back = ok(self.live.owner.get(url(f"/cycles/{out['c']['id']}")))
        assert (back["plan_id"], back["environment"], back["name"]) == (
            w["reg"]["id"],
            "staging",
            "Reg · staging",
        )
        assert out["after"]["state"] == "cycle-created"
        made = out["after"]["data"]["detail"]["cycles"][0]
        assert (made["id"], made["pinned"]) == (back["id"], 3)
        assert out["after"]["data"]["newCycle"]["env"] == "staging"

    @test()
    def test_a_draft_plan_cant_make_a_cycle_raw_409(self, suite_parameter):
        w = self.world()
        out = self.js(
            f"""return await h.fail(a.actions.createCycle("{w["draft"]["id"]}",
              {{ name: "x", environment: "" }}, ctx, "PAY"));"""
        )
        direct = self.live.owner.post(
            url(f"/products/{w['product']['id']}/cycles"),
            json={"plan_id": w["draft"]["id"], "name": "x", "environment": None},
        )
        assert direct.status_code == 409 and out["status"] == 409
        assert out["raw"] == as_sent(direct)
