"""Web adapter for the feature tree, run in node against a live server: the state each URL gives, the tree
model, the selected feature's card and cases, that the search, filters and sort are the server's, the writes
(read back from the server) and a raw error."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_feature, make_product, ok, url
from tests.execution_seed import make_case
from tests.web.live import LiveServer, as_sent, body_of, run_js


@Suite(parameters=support.DATABASES)
class WebTreeAdapter:
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
        """PAY with Checkout › Card and Refunds; two cases under Card, one under Refunds."""
        owner = self.live.owner
        p = make_product(owner, "PAY", name="Payments")
        checkout = make_feature(owner, p["id"], "Checkout")
        card = make_feature(owner, p["id"], "Card", parent_id=checkout["id"])
        refunds = make_feature(owner, p["id"], "Refunds")
        cases = [
            make_case(
                owner, p["id"], card["id"], "Pay with a saved Visa card", status="ready", tags=["smoke"]
            ),
            make_case(owner, p["id"], card["id"], "Card is declined", status="draft"),
            make_case(owner, p["id"], refunds["id"], "Partial refund", status="ready"),
        ]
        return {"product": p, "checkout": checkout, "card": card, "refunds": refunds, "cases": cases}

    def load(self, params, email=None):
        """{ out: the adapter's { state, data }, asked: the cases_list URLs it called }."""
        sign = f"await h.signIn({json.dumps(email)});" if email else "await h.signIn();"
        return run_js(
            self.live,
            f"""{sign}
            const params = {json.dumps({"product": "PAY", **params})};
            const ctx = await h.ctx(params);
            const out = await (await h.adapter("tree")).load(params, ctx);
            const asked = h.calls.map((c) => c.path).filter((p) => p.includes("/products/PAY/cases?"));
            return {{ out, asked }};""",
            "/app?view=tree&product=PAY",
        )

    def act(self, code):
        return run_js(
            self.live,
            f"""await h.signIn();
            const ctx = await h.ctx({{ product: "PAY" }});
            const tree = await h.adapter("tree");
            {code}""",
            "/app?view=tree&product=PAY",
        )

    @test()
    def test_default_selects_the_first_feature_with_cases(self, suite_parameter):
        s = self.seed()
        out = self.load({})["out"]
        assert out["state"] == "default"
        d = out["data"]
        assert d["sel"] == s["card"]["id"] and d["readOnly"] is False
        assert [n["name"] for n in d["tree"]] == ["Checkout", "Refunds"]
        checkout = d["tree"][0]
        assert checkout["open"] is True and [k["name"] for k in checkout["kids"]] == ["Card"]
        card = checkout["kids"][0]
        assert [k["title"] for k in card["kids"]] == ["Pay with a saved Visa card", "Card is declined"]
        first = card["kids"][0]
        assert (first["t"], first["life"], first["ver"]) == ("c", "ready", 1)
        assert d["casesTotal"] == 2 and [c["key"] for c in d["cases"]] == [c["key"] for c in s["cases"][:2]]
        f = d["feature"]
        assert (f["id"], f["name"], f["parent"]) == (s["card"]["id"], "Card", "Checkout")
        assert (f["stats"]["cases"], f["stats"]["ready"], f["stats"]["draft"]) == (2, 1, 1)
        assert d["products"][0]["key"] == "PAY" and d["tags"] == [{"tag": "smoke", "cases": 1}]
        assert self.load({"feature": s["refunds"]["id"]})["out"]["data"]["feature"]["name"] == "Refunds"

    @test()
    def test_no_features_is_the_empty_product_and_new_feature_at_the_root(self, suite_parameter):
        make_product(self.live.owner, "PAY", name="Payments")
        out = self.load({})["out"]
        assert out["state"] == "empty-product" and out["data"]["empty"] is True
        new = self.load({"ui": "new-feature"})["out"]
        assert new["state"] == "new-feature" and new["data"]["newUnder"] == "root"

    @test()
    def test_search_is_the_servers_q(self, suite_parameter):
        s = self.seed()
        got = self.load({"q": "visa"})
        out = got["out"]
        assert out["state"] == "search"
        assert out["data"]["hits"] == 1 and out["data"]["feats"] == 0
        assert [n["name"] for n in out["data"]["tree"]] == ["Checkout"]
        assert [k["key"] for k in out["data"]["tree"][0]["kids"][0]["kids"]] == [s["cases"][0]["key"]]
        assert any("q=visa" in p and "feature=" not in p for p in got["asked"])
        none = self.load({"q": "billing"})["out"]
        assert none["state"] == "search-empty" and none["data"]["tree"] == []

    @test()
    def test_filters_and_sort_are_sent_to_the_server(self, suite_parameter):
        s = self.seed()
        got = self.load({"feature": s["card"]["id"], "status": "ready", "sort": "title"})
        assert got["out"]["state"] == "filters"
        assert got["out"]["data"]["filter"]["status"] == ["ready"]
        assert [c["title"] for c in got["out"]["data"]["cases"]] == ["Pay with a saved Visa card"]
        assert any("status=ready" in p and "sort=title" in p for p in got["asked"])

    @test()
    def test_a_viewer_gets_the_read_only_tree(self, suite_parameter):
        self.seed()
        support.add_member(self.live.owner, "viewer@example.com", "viewer")
        out = self.load({"ui": "new-feature"}, email="viewer@example.com")["out"]
        assert out["state"] == "read-only"
        assert out["data"]["readOnly"] is True and out["data"]["newUnder"] is None

    @test()
    def test_move_dialog_lists_destinations_without_the_feature_itself(self, suite_parameter):
        s = self.seed()
        out = self.load({"feature": s["checkout"]["id"], "ui": "move"})["out"]
        assert out["state"] == "move"
        dests = {x["v"]: x for x in out["data"]["move"]["dests"]}
        assert out["data"]["move"]["src"] == s["checkout"]["id"] and out["data"]["move"]["dest"] == "root"
        assert dests[s["checkout"]["id"]]["dis"] is True and dests[s["card"]["id"]]["dis"] is True
        assert dests[s["refunds"]["id"]]["dis"] is False

    @test()
    def test_create_and_describe_a_feature(self, suite_parameter):
        s = self.seed()
        out = self.act(
            f"""const f = await tree.actions.createFeature("Wallets", {json.dumps(s["checkout"]["id"])}, ctx);
            const md = "Apple Pay and **Google Pay**";
            const u = await tree.actions.updateFeature(f.id, {{ description: {{ markdown: md }} }}, ctx);
            const after = await tree.load({{ product: "PAY", feature: f.id, ui: "desc-saved" }}, ctx);
            return {{ f, u, after }};"""
        )
        back = ok(self.live.owner.get(url(f"/features/{out['f']['id']}")))
        assert (back["name"], back["parent_id"]) == ("Wallets", s["checkout"]["id"])
        assert "Google Pay" in json.dumps(back["description"])
        assert out["after"]["state"] == "desc-saved"
        assert out["after"]["data"]["feature"]["desc"] == "<p>Apple Pay and <b>Google Pay</b></p>"
        assert out["after"]["data"]["feature"]["edited"]["by"]

    @test()
    def test_move_a_feature_and_a_case_then_the_dropped_state(self, suite_parameter):
        s = self.seed()
        case = s["cases"][0]
        out = self.act(
            f"""await tree.actions.moveFeature({json.dumps(s["card"]["id"])}, null, 0, ctx);
            const refunds = {json.dumps(s["refunds"]["id"])};
            await tree.actions.moveCase({json.dumps(case["id"])}, refunds, 0, ctx);
            const card = {json.dumps(s["card"]["id"])}, from = {json.dumps(s["checkout"]["id"])};
            const p = {{ product: "PAY", feature: card, moved: card, from, pos: "0", ui: "dropped" }};
            return await tree.load(p, ctx);"""
        )
        assert ok(self.live.owner.get(url(f"/features/{s['card']['id']}")))["parent_id"] is None
        moved = ok(self.live.owner.get(url(f"/cases/{case['id']}")))
        assert (moved["feature_id"], moved["position"]) == (s["refunds"]["id"], 0)
        assert out["state"] == "dropped"
        assert out["data"]["undo"] == {"kind": "f", "from": s["checkout"]["id"], "pos": 0}
        assert [n["name"] for n in out["data"]["tree"]][0] == "Card"

    @test()
    def test_moving_a_feature_into_its_own_child_is_the_raw_error(self, suite_parameter):
        s = self.seed()
        out = self.act(
            f"""return h.fail(tree.actions.moveFeature({json.dumps(s["checkout"]["id"])},
              {json.dumps(s["card"]["id"])}, 0, ctx));"""
        )
        move = {"parent_id": s["card"]["id"], "position": 0}
        raw = as_sent(self.live.owner.post(url(f"/features/{s['checkout']['id']}/move"), json=move))
        assert body_of(raw)["status"] >= 400
        assert out == {"name": "ApiError", "status": body_of(raw)["status"], "raw": raw}
