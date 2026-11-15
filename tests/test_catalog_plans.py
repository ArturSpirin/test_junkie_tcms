"""Test plans: an ordered list of feature or query entries; removing one renumbers the rest."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import events, make_feature, make_plan, make_product, make_release, ok, url


@Suite(parameters=support.DATABASES)
class CatalogPlans:
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
    def test_create_with_release_and_rich_description(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        r = make_release(owner, p)["id"]
        plan = make_plan(owner, p, "Smoke", release_id=r, description={"markdown": "Run `fast` ones"})
        assert (plan["release_id"], plan["status"], plan["entries"]) == (r, "draft", [])
        assert plan["description"] == "Run `fast` ones"
        assert ok(owner.get(url(f"/plans/{plan['id']}")))["name"] == "Smoke"
        assert [x["id"] for x in ok(owner.get(url("/products/PAY/plans")))["items"]] == [plan["id"]]
        assert owner.get(url("/plans/nope")).status_code == 404

    @test()
    def test_release_must_be_of_the_same_product(self, suite_parameter):
        owner = self.env.owner
        pay = make_product(owner, "PAY")["id"]
        ops = make_product(owner, "OPS")["id"]
        theirs = make_release(owner, ops)["id"]
        assert (
            owner.post(url(f"/products/{pay}/plans"), json={"name": "x", "release_id": theirs}).status_code
            == 422
        )
        plan = make_plan(owner, pay)["id"]
        assert owner.patch(url(f"/plans/{plan}"), json={"release_id": theirs}).status_code == 422

    @test()
    def test_entries_keep_order_and_remove_renumbers(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        a = make_feature(owner, p, "A")["id"]
        b = make_feature(owner, p, "B")["id"]
        plan = make_plan(owner, p)["id"]
        query = {"tags": ["smoke"], "priority": ["P1"], "type": [], "automation": []}
        body = {"entries": [{"feature_id": a}, {"query": query}, {"feature_id": b}]}
        entries = ok(owner.post(url(f"/plans/{plan}/entries"), json=body))["entries"]
        assert [(e["feature_id"], e["query"], e["position"]) for e in entries] == [
            (a, None, 0),
            (None, query, 1),
            (b, None, 2),
        ]
        after = ok(owner.delete(url(f"/plans/{plan}/entries/{entries[0]['id']}")))["entries"]
        assert [(e["id"], e["position"]) for e in after] == [(entries[1]["id"], 0), (entries[2]["id"], 1)]
        more = ok(owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"feature_id": a}]}))["entries"]
        assert [e["position"] for e in more] == [0, 1, 2]
        assert owner.delete(url(f"/plans/{plan}/entries/{entries[0]['id']}")).status_code == 404
        actions = sorted(e["action"] for e in events(owner, "plan"))
        assert actions == ["plan.add_entries", "plan.add_entries", "plan.create", "plan.remove_entry"]

    @test()
    def test_entry_needs_exactly_one_target(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        a = make_feature(owner, p, "A")["id"]
        plan = make_plan(owner, p)["id"]
        both = {"entries": [{"feature_id": a, "query": {"tags": ["x"]}}]}
        assert owner.post(url(f"/plans/{plan}/entries"), json=both).status_code == 422
        assert owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{}]}).status_code == 422
        assert owner.post(url(f"/plans/{plan}/entries"), json={"entries": []}).status_code == 422
        assert (
            owner.post(
                url(f"/plans/{plan}/entries"), json={"entries": [{"query": {"color": ["red"]}}]}
            ).status_code
            == 422
        )
        assert ok(owner.get(url(f"/plans/{plan}")))["entries"] == []

    @test()
    def test_entry_feature_must_be_active_and_in_the_product(self, suite_parameter):
        owner = self.env.owner
        pay = make_product(owner, "PAY")["id"]
        ops = make_product(owner, "OPS")["id"]
        mine = make_feature(owner, pay, "Mine")["id"]
        theirs = make_feature(owner, ops, "Theirs")["id"]
        plan = make_plan(owner, pay)["id"]
        assert (
            owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"feature_id": theirs}]}).status_code
            == 422
        )
        ok(owner.post(url(f"/features/{mine}/archive")))
        assert (
            owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"feature_id": mine}]}).status_code
            == 409
        )

    @test()
    def test_archived_status_hides_the_plan(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        plan = make_plan(owner, p)["id"]
        ok(owner.patch(url(f"/plans/{plan}"), json={"status": "active"}))
        updated = ok(owner.patch(url(f"/plans/{plan}"), json={"status": "archived", "name": "Old smoke"}))
        assert (updated["status"], updated["name"]) == ("archived", "Old smoke")
        assert ok(owner.get(url(f"/products/{p}/plans")))["items"] == []
        assert (
            len(ok(owner.get(url(f"/products/{p}/plans"), params={"include_archived": True}))["items"]) == 1
        )
        updates = [e["changes"] for e in events(owner, "plan") if e["action"] == "plan.update"]
        assert {"name": ["Smoke", "Old smoke"], "status": ["active", "archived"]} in updates

    @test()
    def test_status_moves(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        plan = make_plan(owner, p)["id"]
        patch = lambda body: owner.patch(url(f"/plans/{plan}"), json=body)  # noqa: E731
        assert patch({"status": "archived"}).status_code == 409
        assert ok(patch({"status": "draft"}))["status"] == "draft"  # same status: no move
        assert ok(patch({"status": "active"}))["status"] == "active"
        assert patch({"status": "draft"}).status_code == 409
        assert ok(patch({"status": "archived"}))["status"] == "archived"
        assert patch({"status": "draft"}).status_code == 409
        assert ok(patch({"status": "active", "name": "Back"}))["name"] == "Back"
        moves = [e["changes"]["status"] for e in events(owner, "plan") if "status" in (e["changes"] or {})]
        assert sorted(map(str, moves)) == sorted(
            map(str, [[None, "draft"], ["draft", "active"], ["active", "archived"], ["archived", "active"]])
        )

    @test()
    def test_archived_plan_is_read_only(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        a = make_feature(owner, p, "A")["id"]
        plan = make_plan(owner, p)["id"]
        [entry] = ok(owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"feature_id": a}]}))[
            "entries"
        ]
        ok(owner.patch(url(f"/plans/{plan}"), json={"status": "active"}))
        ok(owner.patch(url(f"/plans/{plan}"), json={"status": "archived"}))
        assert owner.patch(url(f"/plans/{plan}"), json={"name": "x"}).status_code == 409
        assert (
            owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"feature_id": a}]}).status_code
            == 409
        )
        assert owner.delete(url(f"/plans/{plan}/entries/{entry['id']}")).status_code == 409
        order = {"entry_ids": [entry["id"]]}
        assert owner.put(url(f"/plans/{plan}/entries/order"), json=order).status_code == 409
        got = ok(owner.get(url(f"/plans/{plan}")))
        assert (got["name"], len(got["entries"])) == ("Smoke", 1)

    @test()
    def test_entries_from_a_release_expand_once_and_are_not_tied_to_it(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        a = make_feature(owner, p, "A")["id"]
        a1 = make_feature(owner, p, "A1", parent_id=a)["id"]
        b = make_feature(owner, p, "B")["id"]
        gone = make_feature(owner, p, "Gone")["id"]
        other = make_feature(owner, p, "Other")["id"]
        r = make_release(owner, p)["id"]
        ok(owner.put(url(f"/releases/{r}/features"), json={"feature_ids": [b, a1, a, gone]}))
        ok(owner.post(url(f"/features/{gone}/archive")))
        plan = make_plan(owner, p)["id"]
        ok(owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"feature_id": b}]}))
        body = {"entries": [{"release_id": r}, {"release_id": r}]}
        entries = ok(owner.post(url(f"/plans/{plan}/entries"), json=body))["entries"]
        # Tree order (A, A1), B already in the plan, the archived one skipped, the repeat adds nothing.
        assert [(e["feature_id"], e["position"]) for e in entries] == [(b, 0), (a, 1), (a1, 2)]
        [added] = [
            e
            for e in events(owner, "plan")
            if e["action"] == "plan.add_entries" and "release_ids" in e["changes"]
        ]
        assert added["changes"]["release_ids"] == [None, [r]]
        assert (
            ok(owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"release_id": r}]}))["entries"]
            == entries
        )
        assert len([e for e in events(owner, "plan") if e["action"] == "plan.add_entries"]) == 2
        ok(owner.put(url(f"/releases/{r}/features"), json={"feature_ids": [other]}))
        assert ok(owner.get(url(f"/plans/{plan}")))["entries"] == entries

    @test()
    def test_release_entry_must_be_of_the_plans_product(self, suite_parameter):
        owner = self.env.owner
        pay = make_product(owner, "PAY")["id"]
        ops = make_product(owner, "OPS")["id"]
        theirs = make_release(owner, ops)["id"]
        plan = make_plan(owner, pay)["id"]
        body = {"entries": [{"release_id": theirs}]}
        assert owner.post(url(f"/plans/{plan}/entries"), json=body).status_code == 422
        body = {"entries": [{"release_id": "nope"}]}
        assert owner.post(url(f"/plans/{plan}/entries"), json=body).status_code == 422
        mine = make_release(owner, pay)["id"]
        a = make_feature(owner, pay, "A")["id"]
        both = {"entries": [{"release_id": mine, "feature_id": a}]}
        assert owner.post(url(f"/plans/{plan}/entries"), json=both).status_code == 422

    @test()
    def test_reorder_entries(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        feats = [make_feature(owner, p, n)["id"] for n in ("A", "B", "C")]
        plan = make_plan(owner, p)["id"]
        body = {"entries": [{"feature_id": f} for f in feats]}
        ids = [e["id"] for e in ok(owner.post(url(f"/plans/{plan}/entries"), json=body))["entries"]]
        order = url(f"/plans/{plan}/entries/order")
        new = [ids[2], ids[0], ids[1]]
        entries = ok(owner.put(order, json={"entry_ids": new}))["entries"]
        assert [(e["id"], e["position"]) for e in entries] == [(new[0], 0), (new[1], 1), (new[2], 2)]
        assert [e["id"] for e in ok(owner.get(url(f"/plans/{plan}")))["entries"]] == new
        [event] = [e for e in events(owner, "plan") if e["action"] == "plan.reorder_entries"]
        assert event["changes"] == {"order": [ids, new]}
        ok(owner.put(order, json={"entry_ids": new}))  # same order: no event
        assert len([e for e in events(owner, "plan") if e["action"] == "plan.reorder_entries"]) == 1
        for bad in (new[:2], new + ["nope"], [new[0], new[0], new[1]], [new[0], new[1], "nope"]):
            assert owner.put(order, json={"entry_ids": bad}).status_code == 409
        assert [e["id"] for e in ok(owner.get(url(f"/plans/{plan}")))["entries"]] == new

    @test()
    def test_archived_product_refuses_new_plans(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        ok(owner.post(url(f"/products/{p}/archive")))
        assert owner.post(url(f"/products/{p}/plans"), json={"name": "x"}).status_code == 409
