"""Products: create, read by id or key, rich description in and out, update, archive, audit."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import events, make_feature, make_product, ok, url


@Suite(parameters=support.DATABASES)
class CatalogProducts:
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
    def test_create_and_read_by_id_or_key(self, suite_parameter):
        owner = self.env.owner
        created = make_product(owner, "PAY", description={"markdown": "Takes **cards**."})
        assert created["key"] == "PAY"
        assert created["description"] == "Takes **cards**."
        assert created["archived_at"] is None
        assert created["updated_at"]
        assert ok(owner.get(url("/products/PAY")))["id"] == created["id"]
        assert ok(owner.get(url(f"/products/{created['id']}")))["key"] == "PAY"
        assert owner.get(url("/products/NOPE")).status_code == 404

    @test()
    def test_rich_modes(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner, "PAY", description={"markdown": "Takes **cards**."})
        doc = ok(owner.get(url(f"/products/{p['id']}"), params={"rich": "doc"}))["description"]
        assert doc["type"] == "doc"
        para = doc["content"][0]["content"]
        assert para[1] == {"type": "text", "text": "cards", "marks": [{"type": "bold"}]}
        both = ok(owner.get(url(f"/products/{p['id']}"), params={"rich": "both"}))["description"]
        assert both == {"markdown": "Takes **cards**.", "doc": doc}
        assert owner.get(url(f"/products/{p['id']}"), params={"rich": "html"}).status_code == 422

    @test()
    def test_doc_input_and_bad_rich_input(self, suite_parameter):
        owner = self.env.owner
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

    @test()
    def test_key_rules(self, suite_parameter):
        owner = self.env.owner
        make_product(owner, "PAY")
        assert owner.post(url("/products"), json={"key": "PAY", "name": "again"}).status_code == 409
        for key in ("pay", "P", "1PAY", "PAYMENTSXYZ"):
            assert owner.post(url("/products"), json={"key": key, "name": "x"}).status_code == 422, key

    @test()
    def test_update_logs_markdown_before_and_after(self, suite_parameter):
        owner = self.env.owner
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

    @test()
    def test_unchanged_update_writes_no_audit(self, suite_parameter):
        owner = self.env.owner
        make_product(owner, "PAY")
        ok(owner.patch(url("/products/PAY"), json={"name": "PAY product"}))
        assert [e["action"] for e in events(owner, "product")] == ["product.create"]

    @test()
    def test_archive_hides_from_list_and_is_idempotent(self, suite_parameter):
        owner = self.env.owner
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

    @test()
    def test_list_pages_with_a_cursor(self, suite_parameter):
        owner = self.env.owner
        for key in ("AA", "BB", "CC"):
            make_product(owner, key)
        first = ok(owner.get(url("/products"), params={"limit": 2}))
        assert len(first["items"]) == 2 and first["next_cursor"]
        second = ok(owner.get(url("/products"), params={"limit": 2, "cursor": first["next_cursor"]}))
        assert sorted(p["key"] for p in first["items"] + second["items"]) == ["AA", "BB", "CC"]
        assert second["next_cursor"] is None
        assert {first["total"], second["total"]} == {3}

    @test()
    def test_counts_live_features_and_cases(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner, "PAY")["id"]
        make_product(owner, "OPS")
        kept = make_feature(owner, p, "Kept")["id"]
        dropped = make_feature(owner, p, "Dropped")["id"]
        for feature, title in (
            (kept, "a"),
            (kept, "b"),
            (kept, "archived"),
            (dropped, "in an archived feature"),
        ):
            ok(owner.post(url(f"/products/{p}/cases"), json={"feature_id": feature, "title": title}), 201)
        ok(owner.post(url("/cases/PAY-3/archive")))
        ok(owner.post(url(f"/features/{dropped}/archive")))
        got = ok(owner.get(url("/products/PAY")))
        assert (got["feature_count"], got["case_count"]) == (1, 2)
        listed = {
            x["key"]: (x["feature_count"], x["case_count"]) for x in ok(owner.get(url("/products")))["items"]
        }
        assert listed == {"PAY": (1, 2), "OPS": (0, 0)}
