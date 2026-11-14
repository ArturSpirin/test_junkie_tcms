"""Features: a tree per product; move renumbers, archive takes the subtree, archived parents refuse kids."""

from catalog_seed import events, make_feature, make_product, ok, url


def _tree(owner, product, **params):
    def strip(nodes):
        return [(n["name"], n["position"], strip(n["children"])) for n in nodes]

    return strip(ok(owner.get(url(f"/products/{product}/features"), params=params))["items"])


def test_tree_is_nested_and_ordered(owner):
    p = make_product(owner)["id"]
    checkout = make_feature(owner, p, "Checkout", description={"markdown": "# Flow"})
    make_feature(owner, p, "Search")
    make_feature(owner, p, "Card", parent_id=checkout["id"])
    make_feature(owner, p, "Wallet", parent_id=checkout["id"])
    assert checkout["description"] == "# Flow"
    assert _tree(owner, p) == [
        ("Checkout", 0, [("Card", 0, []), ("Wallet", 1, [])]),
        ("Search", 1, []),
    ]
    assert _tree(owner, "PAY") == _tree(owner, p)


def test_get_and_update(owner):
    p = make_product(owner)["id"]
    f = make_feature(owner, p, "Checkout")
    me = owner.get("/api/v1/me").json()
    actor = next(
        m["actor_id"] for m in owner.get(url("/members")).json()["items"] if m["user_id"] == me["user_id"]
    )
    updated = ok(owner.patch(url(f"/features/{f['id']}"), json={"name": "Pay", "owner_actor_id": actor}))
    assert (updated["name"], updated["owner_actor_id"]) == ("Pay", actor)
    assert ok(owner.get(url(f"/features/{f['id']}"), params={"rich": "doc"}))["description"]["type"] == "doc"
    assert owner.patch(url(f"/features/{f['id']}"), json={"owner_actor_id": "nobody"}).status_code == 422
    assert owner.get(url("/features/nope")).status_code == 404
    [update] = [e for e in events(owner, "feature") if e["action"] == "feature.update"]
    assert update["changes"] == {"name": ["Checkout", "Pay"], "owner_actor_id": [None, actor]}


def test_parent_must_be_in_the_same_product(owner):
    pay = make_product(owner, "PAY")["id"]
    ops = make_product(owner, "OPS")["id"]
    other = make_feature(owner, ops, "Deploy")
    assert (
        owner.post(url(f"/products/{pay}/features"), json={"name": "x", "parent_id": other["id"]}).status_code
        == 422
    )
    assert (
        owner.post(url(f"/products/{pay}/features"), json={"name": "x", "owner_actor_id": "nope"}).status_code
        == 422
    )


def test_move_renumbers_both_sibling_lists(owner):
    p = make_product(owner)["id"]
    a = make_feature(owner, p, "A")
    b = make_feature(owner, p, "B")
    make_feature(owner, p, "C")
    a1 = make_feature(owner, p, "A1", parent_id=a["id"])
    moved = ok(owner.post(url(f"/features/{b['id']}/move"), json={"parent_id": a["id"], "position": 0}))
    assert (moved["parent_id"], moved["position"]) == (a["id"], 0)
    assert _tree(owner, p) == [("A", 0, [("B", 0, []), ("A1", 1, [])]), ("C", 1, [])]
    ok(owner.post(url(f"/features/{a1['id']}/move"), json={"parent_id": None, "position": 99}))
    assert _tree(owner, p) == [("A", 0, [("B", 0, [])]), ("C", 1, []), ("A1", 2, [])]
    [first, _] = [e for e in events(owner, "feature") if e["action"] == "feature.move"]
    assert first["changes"] == {"parent_id": [None, a["id"]], "position": [1, 0]}


def test_move_into_own_subtree_is_409(owner):
    p = make_product(owner)["id"]
    a = make_feature(owner, p, "A")
    a1 = make_feature(owner, p, "A1", parent_id=a["id"])
    assert (
        owner.post(url(f"/features/{a['id']}/move"), json={"parent_id": a1["id"], "position": 0}).status_code
        == 409
    )
    assert (
        owner.post(url(f"/features/{a['id']}/move"), json={"parent_id": a["id"], "position": 0}).status_code
        == 409
    )


def test_archive_takes_the_subtree(owner):
    p = make_product(owner)["id"]
    a = make_feature(owner, p, "A")
    a1 = make_feature(owner, p, "A1", parent_id=a["id"])
    a2 = make_feature(owner, p, "A2", parent_id=a1["id"])
    make_feature(owner, p, "B")
    assert ok(owner.post(url(f"/features/{a['id']}/archive")))["archived_at"]
    assert _tree(owner, p) == [("B", 1, [])]
    assert len(_tree(owner, p, include_archived=True)) == 2
    assert ok(owner.get(url(f"/features/{a2['id']}")))["archived_at"]
    [event] = [e for e in events(owner, "feature") if e["action"] == "feature.archive"]
    assert event["changes"] == {"archived": [None, sorted([a["id"], a1["id"], a2["id"]])]}


def test_archived_parent_or_product_refuses_new_features(owner):
    p = make_product(owner)["id"]
    a = make_feature(owner, p, "A")
    b = make_feature(owner, p, "B")
    ok(owner.post(url(f"/features/{a['id']}/archive")))
    assert (
        owner.post(url(f"/products/{p}/features"), json={"name": "x", "parent_id": a["id"]}).status_code
        == 409
    )
    assert (
        owner.post(url(f"/features/{b['id']}/move"), json={"parent_id": a["id"], "position": 0}).status_code
        == 409
    )
    ok(owner.post(url(f"/products/{p}/archive")))
    assert owner.post(url(f"/products/{p}/features"), json={"name": "x"}).status_code == 409
