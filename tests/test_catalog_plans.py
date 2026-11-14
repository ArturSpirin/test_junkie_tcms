"""Test plans: an ordered list of feature or query entries; removing one renumbers the rest."""

from catalog_seed import events, make_feature, make_plan, make_product, make_release, ok, url


def test_create_with_release_and_rich_description(owner):
    p = make_product(owner)["id"]
    r = make_release(owner, p)["id"]
    plan = make_plan(owner, p, "Smoke", release_id=r, description={"markdown": "Run `fast` ones"})
    assert (plan["release_id"], plan["status"], plan["entries"]) == (r, "active", [])
    assert plan["description"] == "Run `fast` ones"
    assert ok(owner.get(url(f"/plans/{plan['id']}")))["name"] == "Smoke"
    assert [x["id"] for x in ok(owner.get(url("/products/PAY/plans")))["items"]] == [plan["id"]]
    assert owner.get(url("/plans/nope")).status_code == 404


def test_release_must_be_of_the_same_product(owner):
    pay = make_product(owner, "PAY")["id"]
    ops = make_product(owner, "OPS")["id"]
    theirs = make_release(owner, ops)["id"]
    assert (
        owner.post(url(f"/products/{pay}/plans"), json={"name": "x", "release_id": theirs}).status_code == 422
    )
    plan = make_plan(owner, pay)["id"]
    assert owner.patch(url(f"/plans/{plan}"), json={"release_id": theirs}).status_code == 422


def test_entries_keep_order_and_remove_renumbers(owner):
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


def test_entry_needs_exactly_one_target(owner):
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


def test_entry_feature_must_be_active_and_in_the_product(owner):
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
        owner.post(url(f"/plans/{plan}/entries"), json={"entries": [{"feature_id": mine}]}).status_code == 409
    )


def test_archived_status_hides_the_plan(owner):
    p = make_product(owner)["id"]
    plan = make_plan(owner, p)["id"]
    updated = ok(owner.patch(url(f"/plans/{plan}"), json={"status": "archived", "name": "Old smoke"}))
    assert (updated["status"], updated["name"]) == ("archived", "Old smoke")
    assert ok(owner.get(url(f"/products/{p}/plans")))["items"] == []
    assert len(ok(owner.get(url(f"/products/{p}/plans"), params={"include_archived": True}))["items"]) == 1
    [update] = [e for e in events(owner, "plan") if e["action"] == "plan.update"]
    assert update["changes"] == {"name": ["Smoke", "Old smoke"], "status": ["active", "archived"]}


def test_archived_product_refuses_new_plans(owner):
    p = make_product(owner)["id"]
    ok(owner.post(url(f"/products/{p}/archive")))
    assert owner.post(url(f"/products/{p}/plans"), json={"name": "x"}).status_code == 409
