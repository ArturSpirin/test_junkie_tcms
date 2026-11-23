"""F2: each case version names how it was made and for whom, and a case lists the cycles it is in."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import ok, seed, url
from tests.execution_seed import make_case, make_cycle, run_seed
from tests.test_cases import patch


def _versions(client, case: str) -> list[dict]:
    return ok(client.get(url(f"/cases/{case}/versions")))["items"]


@Suite(parameters=support.DATABASES)
class Provenance:
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
    def test_a_version_made_in_the_app_says_ui_and_no_token(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        case = make_case(owner, s["product"]["id"], s["child"]["id"], "Pay by card")
        [v1] = _versions(owner, case["id"])
        assert (v1["via"], v1["token_id"], v1["on_behalf_of_user_id"]) == ("ui", None, None)
        full = ok(owner.get(url(f"/cases/{case['id']}/versions/1")))
        assert (full["via"], full["token_id"], full["on_behalf_of_user_id"]) == ("ui", None, None)

    @test()
    def test_a_version_made_by_an_agent_token_names_the_token_and_its_owner(self, suite_parameter):
        owner = self.env.owner
        me = ok(owner.get("/api/v1/me"))
        s = seed(owner)
        case = make_case(owner, s["product"]["id"], s["child"]["id"], "Pay by card")
        agent = ok(owner.post(url("/agents"), json={"name": "bot", "role": "editor"}), 201)
        created = ok(
            owner.post(
                url("/tokens"),
                json={"name": "bot", "scopes": ["read", "write:cases"], "actor_id": agent["id"]},
            ),
            201,
        )
        ok(patch(self.env.bearer(created["token"]), case["id"], 1, {"title": "Pay by card, by bot"}))

        latest, first = _versions(owner, case["id"])
        assert latest["version"] == 2 and first["version"] == 1
        assert (latest["via"], latest["token_id"], latest["on_behalf_of_user_id"]) == (
            "api",
            created["id"],
            me["user_id"],
        )
        assert first["via"] == "ui"  # the earlier version keeps its own provenance
        assert ok(owner.get(url(f"/cases/{case['id']}/versions/2")))["token_id"] == created["id"]

    @test()
    def test_a_member_token_names_the_token_but_no_one_on_behalf(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        case = make_case(owner, s["product"]["id"], s["child"]["id"], "Pay by card")
        created = ok(owner.post(url("/tokens"), json={"name": "ci", "scopes": ["read", "write:cases"]}), 201)
        ok(patch(self.env.bearer(created["token"]), case["id"], 1, {"title": "Pay by card v2"}))
        latest = _versions(owner, case["id"])[0]
        assert (latest["via"], latest["token_id"], latest["on_behalf_of_user_id"]) == (
            "api",
            created["id"],
            None,
        )

    @test()
    def test_a_case_lists_its_cycles_newest_first_with_the_pinned_version(self, suite_parameter):
        owner = self.env.owner
        r = run_seed(owner)
        case = r["case"]
        ok(patch(owner, case["id"], 1, {"title": "Pay by card v2"}))
        second = make_cycle(owner, r["product"]["id"], name="Second", case_ids=[case["id"]])

        cycles = ok(owner.get(url(f"/cases/{case['id']}/cycles")))
        assert [c["cycle_id"] for c in cycles] == [second["id"], r["cycle"]["id"]]
        assert [c["case_version"] for c in cycles] == [2, 1]
        first = cycles[1]
        assert first["cycle_case_id"] == r["cycle_case"]["id"] and first["name"] == r["cycle"]["name"]
        assert first["cycle_status"] == r["cycle"]["status"] and first["status"] == r["cycle_case"]["status"]
        assert ok(owner.get(url(f"/cases/{case['key']}/cycles"))) == cycles  # by key too

    @test()
    def test_a_case_in_no_cycle_lists_none(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        case = make_case(owner, s["product"]["id"], s["child"]["id"], "Pay by card")
        assert ok(owner.get(url(f"/cases/{case['id']}/cycles"))) == []
        assert owner.get(url("/cases/PAY-99/cycles")).status_code == 404

    @test()
    def test_a_token_limited_to_another_product_cant_list_a_cases_cycles(self, suite_parameter):
        owner = self.env.owner
        r = run_seed(owner)
        other = seed(owner, "BBB")
        token = ok(
            owner.post(
                url("/tokens"),
                json={"name": "b-only", "scopes": ["read"], "product_ids": [other["product"]["id"]]},
            ),
            201,
        )["token"]
        limited = self.env.bearer(token)
        assert limited.get(url(f"/cases/{r['case']['id']}/cycles")).status_code == 404
        everything = ok(owner.post(url("/tokens"), json={"name": "all", "scopes": ["read"]}), 201)["token"]
        assert len(ok(self.env.bearer(everything).get(url(f"/cases/{r['case']['id']}/cycles")))) == 1
