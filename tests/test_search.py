"""T6 search: text in the title, preconditions or steps and tags, on each case's current version."""

from catalog_seed import ok, seed, url
from conftest import PASSWORD, bearer, login
from execution_seed import STEPS, make_case


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


def test_text_matches_title_preconditions_and_steps(owner):
    catalog(owner)
    hits = {h["key"]: h["matched_in"] for h in search(owner, q="card")}
    assert hits == {"PAY-1": ["title"], "PAY-2": ["preconditions"], "PAY-3": ["steps"]}
    assert keys(search(owner, q="SIGN IN")) == ["PAY-2"]
    assert search(owner, q="nothing like this") == []


def test_tags_are_case_insensitive_and_all_must_match(owner):
    catalog(owner)
    assert keys(search(owner, tag="SMOKE")) == ["PAY-1", "PAY-2"]
    assert keys(search(owner, tag=["smoke", "Payments"])) == ["PAY-1"]
    assert keys(search(owner, q="card", tag="smoke")) == ["PAY-1", "PAY-2"]


def test_search_needs_text_or_tag(owner):
    catalog(owner)
    assert owner.get(url("/search")).status_code == 422
    assert owner.get(url("/search"), params={"q": "  "}).status_code == 422


def test_search_uses_the_current_version(owner):
    catalog(owner)
    ok(owner.patch(url("/cases/PAY-1"), json={"title": "Refund by voucher"}, headers={"If-Match": '"1"'}))
    assert "PAY-1" not in keys(search(owner, q="card"))
    [hit] = search(owner, q="voucher")
    assert (hit["key"], hit["current_version"]) == ("PAY-1", 2)


def test_search_filters_by_product_and_feature(owner):
    a = catalog(owner, "AAA")
    catalog(owner, "BBB")
    assert keys(search(owner, q="card")) == ["AAA-1", "AAA-2", "AAA-3", "BBB-1", "BBB-2", "BBB-3"]
    assert keys(search(owner, q="card", product="BBB")) == ["BBB-1", "BBB-2", "BBB-3"]
    assert keys(search(owner, q="card", feature=a["parent"]["id"])) == ["AAA-1", "AAA-2", "AAA-3"]


def test_archived_cases_only_on_request(owner):
    catalog(owner)
    ok(owner.post(url("/cases/PAY-1/archive")))
    assert keys(search(owner, tag="payments")) == []
    assert keys(search(owner, tag="payments", include_archived=True)) == ["PAY-1"]


def test_search_pages(owner):
    catalog(owner)
    first = ok(owner.get(url("/search"), params={"q": "card", "limit": 2}))
    rest = ok(owner.get(url("/search"), params={"q": "card", "limit": 2, "cursor": first["next_cursor"]}))
    assert len(first["items"]) == 2 and len(rest["items"]) == 1
    assert keys(first["items"] + rest["items"]) == ["PAY-1", "PAY-2", "PAY-3"]


def test_search_is_org_isolated(owner, client_factory):
    catalog(owner)
    globex = client_factory()
    login(globex, "other@example.com", PASSWORD)
    assert search(globex, "globex", q="card") == []
    assert globex.get(url("/search", "acme"), params={"q": "card"}).status_code in (403, 404)


def test_product_limited_token_finds_only_its_product(owner, client_factory):
    a = catalog(owner, "AAA")
    b = catalog(owner, "BBB")
    token = ok(
        owner.post(
            url("/tokens"), json={"name": "a-only", "scopes": ["read"], "product_ids": [a["product"]["id"]]}
        ),
        201,
    )["token"]
    client = bearer(client_factory, token)
    assert keys(search(client, q="card")) == ["AAA-1", "AAA-2", "AAA-3"]
    assert client.get(url("/search"), params={"q": "card", "product": b["product"]["id"]}).status_code == 404
