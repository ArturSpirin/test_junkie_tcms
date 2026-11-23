"""A product's owner (an active member) and a new product's feature tree copied from another product."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import events, make_feature, make_product, ok, url
from tests.support import add_member, login


def tree(owner, product: str) -> list:
    def strip(nodes):
        return [(n["name"], strip(n["children"])) for n in nodes]

    return strip(ok(owner.get(url(f"/products/{product}/features")))["items"])


@Suite(parameters=support.DATABASES)
class ProductOwnerAndCopy:
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
    def test_owner_is_set_read_changed_and_cleared(self, suite_parameter):
        owner = self.env.owner
        tess = add_member(owner, "tess@example.com", "tester")["actor_id"]
        amy = add_member(owner, "amy@example.com", "viewer")["actor_id"]
        p = make_product(owner, owner_actor_id=tess)
        assert p["owner_actor_id"] == tess
        assert ok(owner.get(url(f"/products/{p['id']}")))["owner_actor_id"] == tess
        path = url(f"/products/{p['id']}")
        assert ok(owner.patch(path, json={"owner_actor_id": amy}))["owner_actor_id"] == amy
        assert ok(owner.patch(path, json={"name": "Renamed"}))["owner_actor_id"] == amy
        assert ok(owner.patch(path, json={"owner_actor_id": None}))["owner_actor_id"] is None
        update = [e for e in events(owner, "product") if e["action"] == "product.update"][0]
        assert "owner_actor_id" in update["changes"]

    @test()
    def test_an_owner_who_is_not_a_member_is_a_422(self, suite_parameter):
        owner = self.env.owner
        gus = self.env.client()
        login(gus, "other@example.com")
        outsider = ok(gus.get("/api/v1/orgs/globex/members"))["items"][0]["actor_id"]
        tess = add_member(owner, "tess@example.com", "tester")
        assert owner.delete(url(f"/members/{tess['user_id']}")).status_code == 204
        agent = ok(owner.post(url("/agents"), json={"name": "bot", "role": "tester"}), 201)["id"]
        for bad in ("nobody", outsider, tess["actor_id"], agent):
            response = owner.post(url("/products"), json={"key": "PAY", "name": "P", "owner_actor_id": bad})
            assert response.status_code == 422, (bad, response.text)
            assert response.headers["content-type"].startswith("application/problem+json")
            assert response.json()["code"] == "owner_not_member"
        p = make_product(owner)
        response = owner.patch(url(f"/products/{p['id']}"), json={"owner_actor_id": tess["actor_id"]})
        assert (response.status_code, response.json()["code"]) == (422, "owner_not_member")

    @test()
    def test_a_new_product_copies_another_products_live_tree(self, suite_parameter):
        owner = self.env.owner
        src = make_product(owner, "PAY")["id"]
        checkout = make_feature(owner, src, "Checkout")
        make_feature(owner, src, "Card", parent_id=checkout["id"])
        make_feature(owner, src, "Wallet", parent_id=checkout["id"])
        gone = make_feature(owner, src, "Old")
        ok(owner.post(url(f"/features/{gone['id']}/archive")))
        copy = make_product(owner, "PAY2", copy_features_from="PAY")["id"]
        assert tree(owner, copy) == [("Checkout", [("Card", []), ("Wallet", [])])]
        assert tree(owner, src) == tree(owner, copy)
        source_ids = {n["id"] for n in ok(owner.get(url(f"/products/{src}/features")))["items"]}
        assert not source_ids & {n["id"] for n in ok(owner.get(url(f"/products/{copy}/features")))["items"]}
        [create] = [e for e in events(owner, "product") if e["entity_id"] == copy]
        assert create["changes"]["features_copied"] == [None, 3]

    @test()
    def test_copying_from_another_orgs_product_is_a_404(self, suite_parameter):
        owner = self.env.owner
        gus = self.env.client()
        login(gus, "other@example.com")
        theirs = make_product(gus, "GLO", org="globex")["id"]
        make_feature(gus, theirs, "Secret", org="globex")
        body = {"key": "PAY", "name": "P", "copy_features_from": theirs}
        response = owner.post(url("/products"), json=body)
        assert response.status_code == 404, response.text
        assert ok(owner.get(url("/products")))["total"] == 0
