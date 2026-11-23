"""T6 reports: release status per case, readiness, stale results, NULLS LAST, and org isolation."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_product, make_release, ok, seed, url
from tests.execution_seed import cycle_cases, make_case, make_cycle, record
from tests.support import PASSWORD, login


def release_seed(owner, key: str = "PAY", n: int = 3, org: str = "acme") -> dict:
    """The catalog seed plus `n` cases under the release's feature, all in one cycle of the release."""
    s = seed(owner, key, org)
    cases = [make_case(owner, s["product"]["id"], s["child"]["id"], f"Case {i}", org) for i in range(n)]
    cycle = make_cycle(
        owner, s["product"]["id"], org, release_id=s["release"]["id"], case_ids=[c["id"] for c in cases]
    )
    by_case = {cc["case_id"]: cc["id"] for cc in cycle_cases(owner, cycle["id"], org)}
    return {**s, "cases": cases, "cycle": cycle, "cc": [by_case[c["id"]] for c in cases]}


def report(client, release: str, org: str = "acme") -> dict:
    return ok(client.get(url(f"/releases/{release}/report", org)))


def cycle_report(client, cycle: str, org: str = "acme") -> dict:
    return ok(client.get(url(f"/cycles/{cycle}/report", org)))


def feature_items(client, s: dict, org: str = "acme") -> list[dict]:
    path = url(f"/features/{s['child']['id']}/report", org)
    return ok(client.get(path, params={"release": s["release"]["id"]}))["items"]


def counts(r: dict, *names: str) -> tuple:
    return tuple(r["counts"][n] for n in names)


@Suite(parameters=support.DATABASES)
class Reports:
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
    def test_release_report_counts_pass_fail_blocked(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner)
        ok(record(owner, s["cc"][0], status="success"), 201)
        ok(record(owner, s["cc"][1], status="fail"), 201)
        ok(record(owner, s["cc"][2], status="skip", comment={"markdown": "Blocked by BUG-7"}), 201)
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "fail", "skip", "untested", "total") == (1, 1, 1, 0, 3)
        assert r["ready"] is False
        assert r["release"]["id"] == s["release"]["id"]
        [feature] = r["features"]
        assert (feature["feature_id"], feature["name"], feature["counts"]["total"]) == (
            s["child"]["id"],
            "Card",
            3,
        )

    @test()
    def test_ready_only_when_nothing_failed_or_untested(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        ok(record(owner, s["cc"][0], status="success"), 201)
        assert report(owner, s["release"]["id"])["ready"] is False
        ok(record(owner, s["cc"][1], status="success"), 201)
        assert report(owner, s["release"]["id"])["ready"] is True

    @test()
    def test_empty_release_is_not_ready(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        r = make_release(owner, s["product"]["id"], "2.0")
        out = report(owner, r["id"])
        assert (out["counts"]["total"], out["ready"]) == (0, False)

    @test()
    def test_case_in_no_cycle_is_untested_and_not_in_cycle(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        make_case(owner, s["product"]["id"], s["child"]["id"], "Forgotten")
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "untested", "not_in_cycle", "total") == (1, 1, 1, 2)
        assert r["ready"] is False

    @test()
    def test_result_on_older_case_version_is_untested_and_stale(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        assert report(owner, s["release"]["id"])["ready"] is True
        case = s["cases"][0]
        edited = owner.patch(
            url(f"/cases/{case['id']}"), json={"title": "Changed"}, headers={"If-Match": '"1"'}
        )
        ok(edited)
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "untested", "stale", "total") == (0, 1, 1, 1)
        assert r["ready"] is False
        [item] = feature_items(owner, s)
        assert (item["status"], item["stale"], item["last_result_status"]) == ("untested", True, "success")
        assert item["last_result_at"] is not None and item["cycle_id"] == s["cycle"]["id"]
        # The cycle report keeps the pinned result and says the pin is behind.
        c = cycle_report(owner, s["cycle"]["id"])
        assert (c["counts"]["success"], c["stale"]) == (1, 1)

    @test()
    def test_stale_case_is_refreshed_and_rerun_in_its_cycle(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        cc, cycle, release = s["cc"][0], s["cycle"]["id"], s["release"]["id"]
        ok(record(owner, cc, status="fail"), 201)
        ok(record(owner, cc, status="success"), 201)
        ok(
            owner.patch(
                url(f"/cases/{s['cases'][0]['id']}"), json={"title": "Changed"}, headers={"If-Match": '"1"'}
            )
        )
        c = cycle_report(owner, cycle)
        assert (c["counts"]["success"], c["stale"]) == (1, 1)

        # Refreshed, not rerun yet: untested on version 2 in the cycle, still stale in the release.
        ok(owner.post(url(f"/cycle-cases/{cc}/refresh-version")))
        r = report(owner, release)
        assert counts(r, "success", "untested", "stale") == (0, 1, 1)
        [item] = feature_items(owner, s)
        assert (item["status"], item["stale"], item["last_result_status"]) == ("untested", True, "success")
        assert item["last_result_at"] is not None
        c = cycle_report(owner, cycle)
        assert (c["counts"]["success"], c["counts"]["untested"], c["stale"]) == (0, 1, 0)

        rerun = ok(record(owner, cc, status="success"), 201)
        assert (rerun["attempt"], rerun["case_version"]) == (3, 2)
        r = report(owner, release)
        assert counts(r, "success", "untested", "stale") == (1, 0, 0)
        assert r["ready"] is True
        [item] = feature_items(owner, s)
        assert (item["status"], item["stale"], item["last_result_status"]) == ("success", False, "success")
        c = cycle_report(owner, cycle)
        assert (c["counts"]["success"], c["stale"]) == (1, 0)

    @test()
    def test_unrun_row_in_newer_cycle_does_not_override_a_result(self, suite_parameter):
        """NULLS LAST: an unrun cycle case sorts after a result on Postgres and SQLite alike."""
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="fail"), 201)
        make_cycle(
            owner,
            s["product"]["id"],
            name="Rerun",
            release_id=s["release"]["id"],
            case_ids=[s["cases"][0]["id"]],
        )
        assert counts(report(owner, s["release"]["id"]), "fail", "untested") == (1, 0)

    @test()
    def test_newest_result_across_cycles_wins(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="fail"), 201)
        rerun = make_cycle(
            owner,
            s["product"]["id"],
            name="Rerun",
            release_id=s["release"]["id"],
            case_ids=[s["cases"][0]["id"]],
        )
        [cc] = cycle_cases(owner, rerun["id"])
        ok(record(owner, cc["id"], status="success"), 201)
        r = report(owner, s["release"]["id"])
        assert counts(r, "success", "fail") == (1, 0)
        assert r["ready"] is True

    @test()
    def test_cycle_outside_the_release_does_not_count(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        other = make_cycle(owner, s["product"]["id"], name="Ad hoc", case_ids=[s["cases"][0]["id"]])
        [cc] = cycle_cases(owner, other["id"])
        ok(record(owner, cc["id"], status="fail"), 201)
        assert counts(report(owner, s["release"]["id"]), "fail", "untested") == (0, 1)

    @test()
    def test_product_report_lists_releases_but_not_cancelled(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        ok(record(owner, s["cc"][0], status="success"), 201)
        gone = make_release(owner, s["product"]["id"], "0.9")
        ok(owner.patch(url(f"/releases/{gone['id']}"), json={"status": "cancelled"}))
        out = ok(owner.get(url(f"/products/{s['product']['id']}/report")))
        assert out["product_key"] == "PAY"
        assert [r["release"]["id"] for r in out["releases"]] == [s["release"]["id"]]
        assert out["releases"][0]["ready"] is True
        one = ok(owner.get(url(f"/products/{s['product']['id']}/report"), params={"release": gone["id"]}))
        assert [r["release"]["id"] for r in one["releases"]] == [gone["id"]]

    @test()
    def test_product_report_refuses_another_products_release(self, suite_parameter):
        owner = self.env.owner
        a = seed(owner, "AAA")
        b = seed(owner, "BBB")
        r = owner.get(url(f"/products/{a['product']['id']}/report"), params={"release": b["release"]["id"]})
        assert r.status_code == 422, r.text

    @test()
    def test_org_report_filters_by_release_status(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        out = ok(owner.get(url("/report")))
        [p] = out["products"]
        assert [r["release"]["id"] for r in p["releases"]] == [s["release"]["id"]]
        ok(owner.patch(url(f"/releases/{s['release']['id']}"), json={"status": "released"}))
        assert ok(owner.get(url("/report")))["products"][0]["releases"] == []
        out = ok(owner.get(url("/report"), params={"release_status": "released"}))
        assert [r["release"]["id"] for r in out["products"][0]["releases"]] == [s["release"]["id"]]
        assert owner.get(url("/report"), params={"release_status": "shipped"}).status_code == 422

    @test()
    def test_feature_report_pages_by_case_number(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=3)
        ok(record(owner, s["cc"][1], status="fail"), 201)
        path = url(f"/features/{s['parent']['id']}/report")
        first = ok(owner.get(path, params={"release": s["release"]["id"], "limit": 2}))
        assert [i["key"] for i in first["items"]] == ["PAY-1", "PAY-2"]
        assert first["items"][1]["status"] == "fail"
        assert first["counts"]["total"] == 3
        rest = ok(
            owner.get(
                path, params={"release": s["release"]["id"], "limit": 2, "cursor": first["next_cursor"]}
            )
        )
        assert ([i["key"] for i in rest["items"]], rest["next_cursor"]) == (["PAY-3"], None)

    @test()
    def test_feature_report_refuses_another_products_release(self, suite_parameter):
        owner = self.env.owner
        a = seed(owner, "AAA")
        b = seed(owner, "BBB")
        r = owner.get(url(f"/features/{a['child']['id']}/report"), params={"release": b["release"]["id"]})
        assert r.status_code == 422, r.text

    @test()
    def test_cycle_report_counts(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=2)
        ok(record(owner, s["cc"][0], status="error"), 201)
        out = ok(owner.get(url(f"/cycles/{s['cycle']['id']}/report")))
        assert (out["counts"]["error"], out["counts"]["untested"], out["total"]) == (1, 1, 2)

    @test()
    def test_reports_are_org_isolated(self, suite_parameter):
        owner = self.env.owner
        s = release_seed(owner, n=1)
        globex = self.env.client()
        login(globex, "other@example.com", PASSWORD)
        make_product(globex, "GLX", org="globex")
        for path, params in (
            (f"/releases/{s['release']['id']}/report", None),
            (f"/features/{s['child']['id']}/report", {"release": s["release"]["id"]}),
            (f"/cycles/{s['cycle']['id']}/report", None),
            (f"/products/{s['product']['id']}/report", None),
        ):
            assert globex.get(url(path, "globex"), params=params).status_code == 404, path
        assert [p["product_key"] for p in ok(globex.get(url("/report", "globex")))["products"]] == ["GLX"]
        assert [p["product_key"] for p in ok(owner.get(url("/report")))["products"]] == ["PAY"]

    @test()
    def test_product_limited_token_sees_only_its_product(self, suite_parameter):
        owner = self.env.owner
        a = release_seed(owner, "AAA", n=1)
        b = release_seed(owner, "BBB", n=1)
        token = ok(
            owner.post(
                url("/tokens"),
                json={"name": "a-only", "scopes": ["read"], "product_ids": [a["product"]["id"]]},
            ),
            201,
        )["token"]
        client = self.env.bearer(token)
        assert [p["product_key"] for p in ok(client.get(url("/report")))["products"]] == ["AAA"]
        assert client.get(url(f"/releases/{b['release']['id']}/report")).status_code == 404
        assert client.get(url(f"/releases/{a['release']['id']}/report")).status_code == 200
