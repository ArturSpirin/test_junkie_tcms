"""Products: create, read by id or key, rich description in and out, update, archive, audit."""

from catalog_seed import events, make_product, ok, url


def test_create_and_read_by_id_or_key(owner):
    created = make_product(owner, "PAY", description={"markdown": "Takes **cards**."})
    assert created["key"] == "PAY"
    assert created["description"] == "Takes **cards**."
    assert created["archived_at"] is None
    assert created["updated_at"]
    assert ok(owner.get(url("/products/PAY")))["id"] == created["id"]
    assert ok(owner.get(url(f"/products/{created['id']}")))["key"] == "PAY"
    assert owner.get(url("/products/NOPE")).status_code == 404


def test_rich_modes(owner):
    p = make_product(owner, "PAY", description={"markdown": "Takes **cards**."})
    doc = ok(owner.get(url(f"/products/{p['id']}"), params={"rich": "doc"}))["description"]
    assert doc["type"] == "doc"
    para = doc["content"][0]["content"]
    assert para[1] == {"type": "text", "text": "cards", "marks": [{"type": "bold"}]}
    both = ok(owner.get(url(f"/products/{p['id']}"), params={"rich": "both"}))["description"]
    assert both == {"markdown": "Takes **cards**.", "doc": doc}
    assert owner.get(url(f"/products/{p['id']}"), params={"rich": "html"}).status_code == 422


def test_doc_input_and_bad_rich_input(owner):
    doc = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hi"}]}]}
    p = make_product(owner, "PAY", description={"doc": doc})
    assert p["description"] == "Hi"
    bad = owner.post(
        url("/products"), json={"key": "BAD", "name": "x", "description": {"doc": {"type": "nope"}}}
    )
    assert bad.status_code == 422
    assert bad.json()["detail"].startswith("description:")
    both = owner.post(
        url("/products"), json={"key": "BAD", "name": "x", "description": {"markdown": "a", "doc": doc}}
    )
    assert both.status_code == 422


def test_key_rules(owner):
    make_product(owner, "PAY")
    assert owner.post(url("/products"), json={"key": "PAY", "name": "again"}).status_code == 409
    for key in ("pay", "P", "1PAY", "PAYMENTSXYZ"):
        assert owner.post(url("/products"), json={"key": key, "name": "x"}).status_code == 422, key


def test_update_logs_markdown_before_and_after(owner):
    p = make_product(owner, "PAY", description={"markdown": "Old"})
    updated = ok(
        owner.patch(url("/products/PAY"), json={"name": "Payments", "description": {"markdown": "New"}})
    )
    assert updated["name"] == "Payments"
    assert updated["description"] == "New"
    assert owner.patch(url("/products/PAY"), json={"key": "NEW"}).status_code == 422
    [update] = [e for e in events(owner, "product") if e["action"] == "product.update"]
    assert update["entity_id"] == p["id"]
    assert update["changes"] == {"name": ["PAY product", "Payments"], "description": ["Old", "New"]}


def test_unchanged_update_writes_no_audit(owner):
    make_product(owner, "PAY")
    ok(owner.patch(url("/products/PAY"), json={"name": "PAY product"}))
    assert [e["action"] for e in events(owner, "product")] == ["product.create"]


def test_archive_hides_from_list_and_is_idempotent(owner):
    make_product(owner, "PAY")
    make_product(owner, "OPS")
    archived = ok(owner.post(url("/products/PAY/archive")))
    assert archived["archived_at"]
    assert ok(owner.post(url("/products/PAY/archive")))["archived_at"] == archived["archived_at"]
    assert [p["key"] for p in ok(owner.get(url("/products")))["items"]] == ["OPS"]
    listed = ok(owner.get(url("/products"), params={"include_archived": True}))["items"]
    assert sorted(p["key"] for p in listed) == ["OPS", "PAY"]
    actions = [e["action"] for e in events(owner, "product")]
    assert sorted(actions) == ["product.archive", "product.create", "product.create"]


def test_list_pages_with_a_cursor(owner):
    for key in ("AA", "BB", "CC"):
        make_product(owner, key)
    first = ok(owner.get(url("/products"), params={"limit": 2}))
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = ok(owner.get(url("/products"), params={"limit": 2, "cursor": first["next_cursor"]}))
    assert sorted(p["key"] for p in first["items"] + second["items"]) == ["AA", "BB", "CC"]
    assert second["next_cursor"] is None
