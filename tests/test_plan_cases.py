"""Plans name cases directly, and resolve to their cases at the current version (T3)."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_feature, make_product, ok, seed, url
from tests.support import login


def make_case(client, product: str, feature: str, title: str, **body) -> dict:
    return ok(
        client.post(url(f"/products/{product}/cases"), json={"feature_id": feature, "title": title, **body}),
        201,
    )


def add(client, plan: str, *entries: dict):
    return client.post(url(f"/plans/{plan}/entries"), json={"entries": list(entries)})


def resolve(client, plan: str) -> list[tuple[str, int, str]]:
    body = ok(client.get(url(f"/plans/{plan}/resolve")))
    assert body["plan_id"] == plan
    return [(i["key"], i["version"], i["title"]) for i in body["items"]]


@Suite(parameters=support.DATABASES)
class PlanCases:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def s(self):
        return seed(self.env.owner)

    @test()
    def test_case_entries_are_checked(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, plan = s["product"]["id"], s["plan"]["id"]
        case = make_case(owner, p, s["child"]["id"], "Pay")
        body = ok(add(owner, plan, {"case_id": case["id"]}))
        assert [e["case_id"] for e in body["entries"]] == [None, case["id"]]
        both = add(owner, plan, {"case_id": case["id"], "feature_id": s["child"]["id"]})
        assert both.status_code == 422
        assert add(owner, plan, {}).status_code == 422
        other = make_product(owner, "SHIP")
        elsewhere = make_case(owner, other["id"], make_feature(owner, other["id"], "Labels")["id"], "Print")
        assert add(owner, plan, {"case_id": elsewhere["id"]}).status_code == 422
        assert add(owner, plan, {"case_id": "01ZZZZZZZZZZZZZZZZZZZZZZZZ"}).status_code == 422
        ok(owner.post(url(f"/cases/{case['id']}/archive")))
        assert add(owner, plan, {"case_id": case["id"]}).status_code == 409
        assert len(ok(owner.get(url(f"/plans/{plan}")))["entries"]) == 2  # nothing added by the failures

    @test()
    def test_case_entries_take_a_key_and_store_the_id(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, plan = s["product"]["id"], s["plan"]["id"]
        first = make_case(owner, p, s["parent"]["id"], "First")
        second = make_case(owner, p, s["parent"]["id"], "Second")
        body = ok(add(owner, plan, {"case_id": "PAY-2"}, {"case_id": first["id"]}))
        assert [e["case_id"] for e in body["entries"]] == [None, second["id"], first["id"]]
        assert [k for k, _, _ in resolve(owner, plan)] == ["PAY-2", "PAY-1"]
        other = make_product(owner, "SHIP")
        make_case(owner, other["id"], make_feature(owner, other["id"], "Labels")["id"], "Print")
        for ref in ("PAY-99", "SHIP-1", "01ZZZZZZZZZZZZZZZZZZZZZZZZ"):
            response = add(owner, plan, {"case_id": ref})
            assert response.status_code == 422, (ref, response.text)
            assert response.json()["detail"] == f"case_id {ref} is not a case of this product"
        ok(owner.post(url("/cases/PAY-1/archive")))
        archived = add(owner, plan, {"case_id": "PAY-1"})
        assert archived.status_code == 409 and archived.json()["detail"] == "Case PAY-1 is archived"
        assert len(ok(owner.get(url(f"/plans/{plan}")))["entries"]) == 3  # nothing added by the failures

    @test()
    def test_resolve_follows_entry_order_once_per_case(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, plan = s["product"]["id"], s["plan"]["id"]
        parent, child = s["parent"]["id"], s["child"]["id"]
        grandchild = make_feature(owner, p, "Refunds", parent_id=child)["id"]
        c1 = make_case(owner, p, child, "Card")
        make_case(owner, p, grandchild, "Refund")
        make_case(owner, p, child, "Wallet")
        top = make_case(owner, p, parent, "Top")
        # seed's plan already has the child feature entry;
        # a direct case entry for an included case adds nothing
        ok(add(owner, plan, {"case_id": top["id"]}, {"case_id": c1["id"]}))
        assert resolve(owner, plan) == [
            ("PAY-1", 1, "Card"),
            ("PAY-2", 1, "Refund"),
            ("PAY-3", 1, "Wallet"),
            ("PAY-4", 1, "Top"),
        ]

    @test()
    def test_resolve_uses_current_version_and_skips_dead_cases(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, plan = s["product"]["id"], s["plan"]["id"]
        child = s["child"]["id"]
        make_case(owner, p, child, "Card")
        make_case(owner, p, child, "Wallet")
        make_case(owner, p, child, "Old")
        edited = owner.patch(url("/cases/PAY-1"), json={"title": "Card v2"}, headers={"If-Match": '"1"'})
        ok(edited)
        ok(owner.post(url("/cases/PAY-2/archive")))
        ok(owner.patch(url("/cases/PAY-3"), json={"status": "deprecated"}, headers={"If-Match": '"1"'}))
        assert resolve(owner, plan) == [("PAY-1", 2, "Card v2")]

    @test()
    def test_resolve_query_entries(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p = s["product"]["id"]
        child = s["child"]["id"]
        plan = ok(owner.post(url(f"/products/{p}/plans"), json={"name": "Smoke"}), 201)["id"]
        make_case(owner, p, child, "Card", tags=["smoke"], priority="high")
        make_case(owner, p, child, "Wallet", tags=["smoke"], priority="low")
        make_case(owner, p, child, "Refund", tags=["regression"], priority="high")
        make_case(owner, p, child, "Auto", priority="high", automation="automated")
        ok(add(owner, plan, {"query": {"tags": ["Smoke", "regression"], "priority": ["high"]}}))
        assert [k for k, _, _ in resolve(owner, plan)] == ["PAY-1", "PAY-3"]
        ok(add(owner, plan, {"query": {"automation": ["automated"]}}))
        assert [k for k, _, _ in resolve(owner, plan)] == ["PAY-1", "PAY-3", "PAY-4"]

    @test()
    def test_resolve_is_tenant_scoped(self, suite_parameter):
        s = self.s()
        other = self.env.client()
        login(other, "other@example.com")
        for org in ("globex", "acme"):
            assert other.get(url(f"/plans/{s['plan']['id']}/resolve", org)).status_code == 404
