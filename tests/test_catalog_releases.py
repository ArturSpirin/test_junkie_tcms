"""Releases: owned by a product, versions unique per product, listing the features they affect."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import events, make_feature, make_product, make_release, ok, url


@Suite(parameters=support.DATABASES)
class CatalogReleases:
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
    def test_create_list_get(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        r = make_release(owner, p, "1.0", notes={"markdown": "- fixes\n- speed"}, target_date="2027-01-15")
        assert (r["status"], r["released_at"], r["feature_ids"]) == ("planned", None, [])
        assert r["notes"] == "- fixes\n- speed"
        assert r["target_date"] == "2027-01-15"
        assert ok(owner.get(url(f"/releases/{r['id']}")))["version"] == "1.0"
        assert [x["id"] for x in ok(owner.get(url("/products/PAY/releases")))["items"]] == [r["id"]]
        assert owner.get(url("/releases/nope")).status_code == 404

    @test()
    def test_version_is_unique_per_product(self, suite_parameter):
        owner = self.env.owner
        pay = make_product(owner, "PAY")["id"]
        ops = make_product(owner, "OPS")["id"]
        make_release(owner, pay, "1.0")
        make_release(owner, ops, "1.0")
        assert (
            owner.post(url(f"/products/{pay}/releases"), json={"version": "1.0", "name": "x"}).status_code
            == 409
        )
        second = make_release(owner, pay, "2.0")
        assert owner.patch(url(f"/releases/{second['id']}"), json={"version": "1.0"}).status_code == 409

    @test()
    def test_released_status_sets_released_at(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        assert make_release(owner, p, "0.9", status="released")["released_at"]
        r = make_release(owner, p, "1.0")
        updated = ok(
            owner.patch(
                url(f"/releases/{r['id']}"), json={"status": "released", "notes": {"markdown": "Out"}}
            )
        )
        assert updated["released_at"]
        assert updated["notes"] == "Out"
        assert owner.patch(url(f"/releases/{r['id']}"), json={"status": "shipped"}).status_code == 422
        [update] = [e for e in events(owner, "release") if e["action"] == "release.update"]
        assert update["changes"]["status"] == ["planned", "released"]
        assert update["changes"]["notes"] == ["", "Out"]
        assert update["changes"]["released_at"][0] is None

    @test()
    def test_set_features_replaces_the_list(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        a = make_feature(owner, p, "A")["id"]
        b = make_feature(owner, p, "B")["id"]
        r = make_release(owner, p)["id"]
        assert ok(owner.put(url(f"/releases/{r}/features"), json={"feature_ids": [b, a, a]}))[
            "feature_ids"
        ] == sorted([a, b])
        assert ok(owner.put(url(f"/releases/{r}/features"), json={"feature_ids": [b]}))["feature_ids"] == [b]
        assert ok(owner.put(url(f"/releases/{r}/features"), json={"feature_ids": [b]}))["feature_ids"] == [b]
        changes = [e["changes"] for e in events(owner, "release") if e["action"] == "release.set_features"]
        assert sorted(map(str, changes)) == sorted(
            map(str, [{"feature_ids": [[], sorted([a, b])]}, {"feature_ids": [sorted([a, b]), [b]]}])
        )

    @test()
    def test_set_features_refuses_other_products_and_archived(self, suite_parameter):
        owner = self.env.owner
        pay = make_product(owner, "PAY")["id"]
        ops = make_product(owner, "OPS")["id"]
        mine = make_feature(owner, pay, "Mine")["id"]
        theirs = make_feature(owner, ops, "Theirs")["id"]
        r = make_release(owner, pay)["id"]
        assert owner.put(url(f"/releases/{r}/features"), json={"feature_ids": [theirs]}).status_code == 422
        assert owner.put(url(f"/releases/{r}/features"), json={"feature_ids": ["nope"]}).status_code == 422
        ok(owner.post(url(f"/features/{mine}/archive")))
        assert owner.put(url(f"/releases/{r}/features"), json={"feature_ids": [mine]}).status_code == 409
        assert ok(owner.get(url(f"/releases/{r}")))["feature_ids"] == []

    @test()
    def test_archived_product_refuses_new_releases(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        ok(owner.post(url(f"/products/{p}/archive")))
        assert (
            owner.post(url(f"/products/{p}/releases"), json={"version": "1", "name": "x"}).status_code == 409
        )
