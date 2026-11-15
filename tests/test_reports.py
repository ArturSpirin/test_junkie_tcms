"""T6 reports: release status per case, readiness, stale results, NULLS LAST, and org isolation."""

from catalog_seed import make_product, make_release, ok, seed, url
from conftest import PASSWORD, bearer, login
from execution_seed import cycle_cases, make_case, make_cycle, record


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


def counts(r: dict, *names: str) -> tuple:
    return tuple(r["counts"][n] for n in names)


def test_release_report_counts_pass_fail_blocked(owner):
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


def test_ready_only_when_nothing_failed_or_untested(owner):
    s = release_seed(owner, n=2)
    ok(record(owner, s["cc"][0], status="success"), 201)
    assert report(owner, s["release"]["id"])["ready"] is False
    ok(record(owner, s["cc"][1], status="success"), 201)
    assert report(owner, s["release"]["id"])["ready"] is True


def test_empty_release_is_not_ready(owner):
    s = seed(owner)
    r = make_release(owner, s["product"]["id"], "2.0")
    out = report(owner, r["id"])
    assert (out["counts"]["total"], out["ready"]) == (0, False)


def test_case_in_no_cycle_is_untested_and_not_in_cycle(owner):
    s = release_seed(owner, n=1)
    ok(record(owner, s["cc"][0], status="success"), 201)
    make_case(owner, s["product"]["id"], s["child"]["id"], "Forgotten")
    r = report(owner, s["release"]["id"])
    assert counts(r, "success", "untested", "not_in_cycle", "total") == (1, 1, 1, 2)
    assert r["ready"] is False


def test_result_on_older_case_version_is_untested_and_stale(owner):
    s = release_seed(owner, n=1)
    ok(record(owner, s["cc"][0], status="success"), 201)
    assert report(owner, s["release"]["id"])["ready"] is True
    case = s["cases"][0]
    edited = owner.patch(url(f"/cases/{case['id']}"), json={"title": "Changed"}, headers={"If-Match": '"1"'})
    ok(edited)
    r = report(owner, s["release"]["id"])
    assert counts(r, "success", "untested", "stale", "total") == (0, 1, 1, 1)
    assert r["ready"] is False
    items = ok(
        owner.get(url(f"/features/{s['child']['id']}/report"), params={"release": s["release"]["id"]})
    )["items"]
    assert (items[0]["status"], items[0]["stale"]) == ("untested", True)


def test_unrun_row_in_newer_cycle_does_not_override_a_result(owner):
    """NULLS LAST: an unrun cycle case sorts after a result on Postgres and SQLite alike."""
    s = release_seed(owner, n=1)
    ok(record(owner, s["cc"][0], status="fail"), 201)
    make_cycle(
        owner, s["product"]["id"], name="Rerun", release_id=s["release"]["id"], case_ids=[s["cases"][0]["id"]]
    )
    assert counts(report(owner, s["release"]["id"]), "fail", "untested") == (1, 0)


def test_newest_result_across_cycles_wins(owner):
    s = release_seed(owner, n=1)
    ok(record(owner, s["cc"][0], status="fail"), 201)
    rerun = make_cycle(
        owner, s["product"]["id"], name="Rerun", release_id=s["release"]["id"], case_ids=[s["cases"][0]["id"]]
    )
    [cc] = cycle_cases(owner, rerun["id"])
    ok(record(owner, cc["id"], status="success"), 201)
    r = report(owner, s["release"]["id"])
    assert counts(r, "success", "fail") == (1, 0)
    assert r["ready"] is True


def test_cycle_outside_the_release_does_not_count(owner):
    s = release_seed(owner, n=1)
    other = make_cycle(owner, s["product"]["id"], name="Ad hoc", case_ids=[s["cases"][0]["id"]])
    [cc] = cycle_cases(owner, other["id"])
    ok(record(owner, cc["id"], status="fail"), 201)
    assert counts(report(owner, s["release"]["id"]), "fail", "untested") == (0, 1)


def test_product_report_lists_releases_but_not_cancelled(owner):
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


def test_product_report_refuses_another_products_release(owner):
    a = seed(owner, "AAA")
    b = seed(owner, "BBB")
    r = owner.get(url(f"/products/{a['product']['id']}/report"), params={"release": b["release"]["id"]})
    assert r.status_code == 422, r.text


def test_org_report_filters_by_release_status(owner):
    s = release_seed(owner, n=1)
    out = ok(owner.get(url("/report")))
    [p] = out["products"]
    assert [r["release"]["id"] for r in p["releases"]] == [s["release"]["id"]]
    ok(owner.patch(url(f"/releases/{s['release']['id']}"), json={"status": "released"}))
    assert ok(owner.get(url("/report")))["products"][0]["releases"] == []
    out = ok(owner.get(url("/report"), params={"release_status": "released"}))
    assert [r["release"]["id"] for r in out["products"][0]["releases"]] == [s["release"]["id"]]
    assert owner.get(url("/report"), params={"release_status": "shipped"}).status_code == 422


def test_feature_report_pages_by_case_number(owner):
    s = release_seed(owner, n=3)
    ok(record(owner, s["cc"][1], status="fail"), 201)
    path = url(f"/features/{s['parent']['id']}/report")
    first = ok(owner.get(path, params={"release": s["release"]["id"], "limit": 2}))
    assert [i["key"] for i in first["items"]] == ["PAY-1", "PAY-2"]
    assert first["items"][1]["status"] == "fail"
    assert first["counts"]["total"] == 3
    rest = ok(
        owner.get(path, params={"release": s["release"]["id"], "limit": 2, "cursor": first["next_cursor"]})
    )
    assert ([i["key"] for i in rest["items"]], rest["next_cursor"]) == (["PAY-3"], None)


def test_feature_report_refuses_another_products_release(owner):
    a = seed(owner, "AAA")
    b = seed(owner, "BBB")
    r = owner.get(url(f"/features/{a['child']['id']}/report"), params={"release": b["release"]["id"]})
    assert r.status_code == 422, r.text


def test_cycle_report_counts(owner):
    s = release_seed(owner, n=2)
    ok(record(owner, s["cc"][0], status="error"), 201)
    out = ok(owner.get(url(f"/cycles/{s['cycle']['id']}/report")))
    assert (out["counts"]["error"], out["counts"]["untested"], out["total"]) == (1, 1, 2)


def test_reports_are_org_isolated(owner, client_factory):
    s = release_seed(owner, n=1)
    globex = client_factory()
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


def test_product_limited_token_sees_only_its_product(owner, client_factory):
    a = release_seed(owner, "AAA", n=1)
    b = release_seed(owner, "BBB", n=1)
    token = ok(
        owner.post(
            url("/tokens"), json={"name": "a-only", "scopes": ["read"], "product_ids": [a["product"]["id"]]}
        ),
        201,
    )["token"]
    client = bearer(client_factory, token)
    assert [p["product_key"] for p in ok(client.get(url("/report")))["products"]] == ["AAA"]
    assert client.get(url(f"/releases/{b['release']['id']}/report")).status_code == 404
    assert client.get(url(f"/releases/{a['release']['id']}/report")).status_code == 200
