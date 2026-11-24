"""`q` on the products, features, plans, members and consumers lists: case-insensitive, across every page."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_feature, make_plan, make_product, ok, url
from tests.support import add_member


def walk(client, path: str, **params) -> tuple[list[dict], int]:
    """Every item of a list one row per page, and the total the first page gave."""
    items, cursor, total = [], None, None
    while True:
        paging = {"limit": 1, "cursor": cursor} if cursor else {"limit": 1}
        page = ok(client.get(url(path), params={**params, **paging}))
        total = page["total"] if total is None else total
        items += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            return items, total


def pair(env, owner, name: str, product: str) -> None:
    pairing = ok(env.client().post("/api/v1/pair", json=None), 201)
    body = {"user_code": pairing["user_code"], "name": name, "product_ids": [product]}
    ok(owner.post(url("/pair/approve"), json=body), 201)


@Suite(parameters=support.DATABASES)
class NameSearch:
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
    def test_products_q_holds_across_pages(self, suite_parameter):
        owner = self.env.owner
        for key, name in (("PAY", "Payments"), ("PAYO", "Payouts"), ("SHOP", "Shop front")):
            make_product(owner, key, name=name)
        items, total = walk(owner, "/products", q="pay")
        assert (sorted(p["name"] for p in items), total) == (["Payments", "Payouts"], 2)
        assert walk(owner, "/products", q="  ")[1] == 3

    @test()
    def test_plans_q_holds_across_pages(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        for name in ("Smoke", "Nightly SMOKE", "Regression"):
            make_plan(owner, p, name)
        items, total = walk(owner, f"/products/{p}/plans", q="smoke")
        assert (sorted(i["name"] for i in items), total) == (["Nightly SMOKE", "Smoke"], 2)

    @test()
    def test_q_matches_percent_and_underscore_literally(self, suite_parameter):
        owner = self.env.owner
        make_product(owner, "AA", name="100% done")
        make_product(owner, "BB", name="1000 done")
        assert [p["name"] for p in walk(owner, "/products", q="0%")[0]] == ["100% done"]

    @test()
    def test_members_q_matches_name_or_email(self, suite_parameter):
        owner = self.env.owner
        add_member(owner, "zed.one@zmail.test", "tester")
        add_member(owner, "zed.two@zmail.test", "viewer")
        add_member(owner, "amy@example.com", "viewer")
        items, total = walk(owner, "/members", q="ZMAIL")
        assert (len(items), total) == (2, 2)
        [amy] = walk(owner, "/members", q="amy")[0]
        assert amy["email"] == "amy@example.com"

    @test()
    def test_consumers_q_holds_across_pages(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        for name in ("build-box", "Build-Server", "laptop"):
            pair(self.env, owner, name, p)
        items, total = walk(owner, "/consumers", q="BUILD")
        assert (sorted(c["name"] for c in items), total) == (["Build-Server", "build-box"], 2)

    @test()
    def test_features_q_keeps_each_matchs_parents(self, suite_parameter):
        owner = self.env.owner
        p = make_product(owner)["id"]
        checkout = make_feature(owner, p, "Checkout")
        card = make_feature(owner, p, "Card", parent_id=checkout["id"])
        make_feature(owner, p, "Wallet", parent_id=checkout["id"])
        make_feature(owner, p, "Search")
        tree = ok(owner.get(url(f"/products/{p}/features"), params={"q": "CARD"}))["items"]
        assert [(n["name"], [c["name"] for c in n["children"]]) for n in tree] == [("Checkout", ["Card"])]
        assert tree[0]["children"][0]["id"] == card["id"]
