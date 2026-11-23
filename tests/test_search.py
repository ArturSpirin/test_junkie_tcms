"""T6 search: text in the title, preconditions or steps and tags, on each case's current version."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import ok, seed, url
from tests.execution_seed import STEPS, make_case
from tests.support import PASSWORD, login


def search(client, org: str = "acme", **params) -> list[dict]:
    return ok(client.get(url("/search", org), params=params))["items"]


def keys(items: list[dict]) -> list[str]:
    return sorted(i["key"] for i in items)


def catalog(owner, key: str = "PAY") -> dict:
    s = seed(owner, key)
    p, f = s["product"]["id"], s["child"]["id"]
    make_case(owner, p, f, "Refund by card", tags=["Smoke", "payments"])
    make_case(owner, p, f, "Sign in", preconditions={"markdown": "A saved CARD exists"}, tags=["smoke"])
    make_case(owner, p, f, "Checkout", steps=STEPS)
    return s


@Suite(parameters=support.DATABASES)
class Search:
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
    def test_text_matches_title_preconditions_and_steps(self, suite_parameter):
        owner = self.env.owner
        catalog(owner)
        hits = {h["key"]: h["matched_in"] for h in search(owner, q="card")}
        assert hits == {"PAY-1": ["title"], "PAY-2": ["preconditions"], "PAY-3": ["steps"]}
        assert keys(search(owner, q="SIGN IN")) == ["PAY-2"]
        assert search(owner, q="nothing like this") == []

    @test()
    def test_text_matches_the_description(self, suite_parameter):
        owner = self.env.owner
        s = catalog(owner)
        make_case(
            owner,
            s["product"]["id"],
            s["child"]["id"],
            "Wallet",
            description={"markdown": "Pays by **card** too"},
        )
        hits = {h["key"]: h["matched_in"] for h in search(owner, q="card")}
        assert hits["PAY-4"] == ["description"]

    @test()
    def test_tags_are_case_insensitive_and_all_must_match(self, suite_parameter):
        owner = self.env.owner
        catalog(owner)
        assert keys(search(owner, tag="SMOKE")) == ["PAY-1", "PAY-2"]
        assert keys(search(owner, tag=["smoke", "Payments"])) == ["PAY-1"]
        assert keys(search(owner, q="card", tag="smoke")) == ["PAY-1", "PAY-2"]

    @test()
    def test_search_needs_text_or_tag(self, suite_parameter):
        owner = self.env.owner
        catalog(owner)
        assert owner.get(url("/search")).status_code == 422
        assert owner.get(url("/search"), params={"q": "  "}).status_code == 422

    @test()
    def test_search_uses_the_current_version(self, suite_parameter):
        owner = self.env.owner
        catalog(owner)
        ok(owner.patch(url("/cases/PAY-1"), json={"title": "Refund by voucher"}, headers={"If-Match": '"1"'}))
        assert "PAY-1" not in keys(search(owner, q="card"))
        [hit] = search(owner, q="voucher")
        assert (hit["key"], hit["current_version"]) == ("PAY-1", 2)

    @test()
    def test_search_filters_by_product_and_feature(self, suite_parameter):
        owner = self.env.owner
        a = catalog(owner, "AAA")
        catalog(owner, "BBB")
        assert keys(search(owner, q="card")) == ["AAA-1", "AAA-2", "AAA-3", "BBB-1", "BBB-2", "BBB-3"]
        assert keys(search(owner, q="card", product="BBB")) == ["BBB-1", "BBB-2", "BBB-3"]
        assert keys(search(owner, q="card", feature=a["parent"]["id"])) == ["AAA-1", "AAA-2", "AAA-3"]

    @test()
    def test_archived_cases_only_on_request(self, suite_parameter):
        owner = self.env.owner
        catalog(owner)
        ok(owner.post(url("/cases/PAY-1/archive")))
        assert keys(search(owner, tag="payments")) == []
        assert keys(search(owner, tag="payments", include_archived=True)) == ["PAY-1"]

    @test()
    def test_search_pages(self, suite_parameter):
        owner = self.env.owner
        catalog(owner)
        first = ok(owner.get(url("/search"), params={"q": "card", "limit": 2}))
        rest = ok(owner.get(url("/search"), params={"q": "card", "limit": 2, "cursor": first["next_cursor"]}))
        assert len(first["items"]) == 2 and len(rest["items"]) == 1
        assert keys(first["items"] + rest["items"]) == ["PAY-1", "PAY-2", "PAY-3"]

    @test()
    def test_search_is_org_isolated(self, suite_parameter):
        owner = self.env.owner
        catalog(owner)
        globex = self.env.client()
        login(globex, "other@example.com", PASSWORD)
        assert search(globex, "globex", q="card") == []
        assert globex.get(url("/search", "acme"), params={"q": "card"}).status_code in (403, 404)

    @test()
    def test_product_limited_token_finds_only_its_product(self, suite_parameter):
        owner = self.env.owner
        a = catalog(owner, "AAA")
        b = catalog(owner, "BBB")
        token = ok(
            owner.post(
                url("/tokens"),
                json={"name": "a-only", "scopes": ["read"], "product_ids": [a["product"]["id"]]},
            ),
            201,
        )["token"]
        client = self.env.bearer(token)
        assert keys(search(client, q="card")) == ["AAA-1", "AAA-2", "AAA-3"]
        assert (
            client.get(url("/search"), params={"q": "card", "product": b["product"]["id"]}).status_code == 404
        )
