"""Cycles: their sources, preview, the active-plan rule, cases, assignees, close and reopen (T4)."""

from catalog_seed import events, ok, seed, url
from conftest import add_member, login
from execution_seed import STEPS, activate, cycle_cases, make_case, make_cycle, record, run_seed

UNTESTED = {"untested": 1, "success": 0, "fail": 0, "error": 0, "ignore": 0, "skip": 0, "cancel": 0}


def test_cycle_from_an_active_plan_pins_its_cases_and_takes_its_release(owner):
    s = seed(owner)
    p = s["product"]["id"]
    case = make_case(owner, p, s["child"]["id"], "Card", steps=STEPS)
    make_case(owner, p, s["parent"]["id"], "Not in the plan")
    activate(owner, s["plan"]["id"])
    cycle = make_cycle(owner, p, plan_id=s["plan"]["id"], environment="staging")
    assert (cycle["plan_id"], cycle["release_id"], cycle["status"]) == (
        s["plan"]["id"],
        s["release"]["id"],
        "open",
    )
    assert cycle["counts"] == UNTESTED
    [cc] = cycle_cases(owner, cycle["id"])
    assert (cc["case_id"], cc["key"], cc["case_version"], cc["status"]) == (
        case["id"],
        "PAY-1",
        1,
        "untested",
    )
    assert [st["id"] for st in cc["steps"]] == [st["id"] for st in case["steps"]]
    [event] = events(owner, "cycle")
    assert event["action"] == "cycle.create"


def test_only_an_active_plan_starts_a_cycle(owner):
    s = seed(owner)
    response = owner.post(
        url(f"/products/{s['product']['id']}/cycles"), json={"name": "R", "plan_id": s["plan"]["id"]}
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "plan_not_active"
    assert ok(owner.get(url(f"/products/{s['product']['id']}/cycles")))["items"] == []


def test_one_source_at_most(owner):
    s = seed(owner)
    p = s["product"]["id"]
    body = {"name": "R", "product_id": p, "feature_ids": [s["child"]["id"]]}
    assert owner.post(url(f"/products/{p}/cycles"), json=body).status_code == 422
    assert make_cycle(owner, p)["counts"]["untested"] == 0  # no source: an empty cycle


def test_product_and_feature_sources_leave_out_archived_and_deprecated_cases(owner):
    s = seed(owner)
    p = s["product"]["id"]
    make_case(owner, p, s["parent"]["id"], "Parent case")
    make_case(owner, p, s["child"]["id"], "Child case")
    make_case(owner, p, s["child"]["id"], "Archived")
    make_case(owner, p, s["child"]["id"], "Deprecated")
    ok(owner.post(url("/cases/PAY-3/archive")))
    ok(owner.patch(url("/cases/PAY-4"), json={"status": "deprecated"}, headers={"If-Match": '"1"'}))

    whole = make_cycle(owner, p, product_id=p)
    assert [c["key"] for c in cycle_cases(owner, whole["id"])] == ["PAY-1", "PAY-2"]
    # The parent feature brings its sub-features' cases too.
    tree = make_cycle(owner, p, feature_ids=[s["parent"]["id"]])
    assert sorted(c["key"] for c in cycle_cases(owner, tree["id"])) == ["PAY-1", "PAY-2"]
    child = make_cycle(owner, p, feature_ids=[s["child"]["id"]])
    assert [c["key"] for c in cycle_cases(owner, child["id"])] == ["PAY-2"]


def test_preview_counts_per_feature_and_writes_nothing(owner):
    s = seed(owner)
    p = s["product"]["id"]
    make_case(owner, p, s["parent"]["id"], "A")
    make_case(owner, p, s["child"]["id"], "B")
    make_case(owner, p, s["child"]["id"], "C")
    ok(owner.post(url("/cases/PAY-3/archive")))
    preview = ok(owner.post(url(f"/products/{p}/cycles/preview"), json={"product_id": p}))
    assert preview["total"] == 2
    assert {f["feature_id"]: f["cases"] for f in preview["features"]} == {
        s["parent"]["id"]: 1,
        s["child"]["id"]: 1,
    }
    assert preview["skipped"] == {"archived": 1, "deprecated": 0}
    assert ok(owner.get(url(f"/products/{p}/cycles")))["items"] == []
    draft = owner.post(url(f"/products/{p}/cycles/preview"), json={"plan_id": s["plan"]["id"]})
    assert draft.status_code == 409 and draft.json()["code"] == "plan_not_active"


def test_cases_from_another_product_are_refused(owner):
    s = seed(owner)
    other = seed(owner, "OPS")
    case = make_case(owner, other["product"]["id"], other["child"]["id"], "Elsewhere")
    p = s["product"]["id"]
    assert (
        owner.post(url(f"/products/{p}/cycles"), json={"name": "R", "case_ids": [case["id"]]}).status_code
        == 422
    )
    plan = other["plan"]["id"]
    activate(owner, plan)
    assert owner.post(url(f"/products/{p}/cycles"), json={"name": "R", "plan_id": plan}).status_code == 422


def test_adding_cases_lists_the_ones_already_present(owner):
    s = run_seed(owner)
    p = s["product"]["id"]
    second = make_case(owner, p, s["parent"]["id"], "Second")
    added = ok(
        owner.post(
            url(f"/cycles/{s['cycle']['id']}/cases"), json={"case_ids": [s["case"]["id"], second["id"]]}
        )
    )
    assert added == {"added": [second["id"]], "already_present": [s["case"]["id"]]}
    assert [c["position"] for c in cycle_cases(owner, s["cycle"]["id"])] == [1, 2]


def test_assign_and_filter_by_assignee(owner):
    s = run_seed(owner)
    actor = add_member(owner, "tess@example.com", "tester")["actor_id"]
    cc = ok(
        owner.post(url(f"/cycle-cases/{s['cycle_case']['id']}/assign"), json={"assignee_actor_id": actor})
    )
    assert cc["assignee_actor_id"] == actor
    assert [c["id"] for c in cycle_cases(owner, s["cycle"]["id"], assignee=actor)] == [cc["id"]]
    assert cycle_cases(owner, s["cycle"]["id"], status="fail") == []
    unknown = owner.post(url(f"/cycle-cases/{cc['id']}/assign"), json={"assignee_actor_id": "nobody"})
    assert unknown.status_code == 422, unknown.text


def test_a_closed_cycle_takes_no_results_or_cases_until_it_reopens(owner):
    s = run_seed(owner)
    cycle, cc = s["cycle"]["id"], s["cycle_case"]["id"]
    closed = ok(owner.post(url(f"/cycles/{cycle}/close")))
    assert closed["status"] == "closed" and closed["closed_at"] is not None
    refused = record(owner, cc, status="success")
    assert refused.status_code == 409 and refused.json()["code"] == "cycle_closed"
    more = owner.post(url(f"/cycles/{cycle}/cases"), json={"case_ids": [s["case"]["id"]]})
    assert more.status_code == 409 and more.json()["code"] == "cycle_closed"
    assert ok(owner.get(url(f"/products/{s['product']['id']}/cycles"), params={"status": "closed"}))["items"]
    reopened = ok(owner.post(url(f"/cycles/{cycle}/reopen")))
    assert (reopened["status"], reopened["closed_at"]) == ("open", None)
    ok(record(owner, cc, status="success"), 201)


def test_rename_a_cycle(owner):
    s = run_seed(owner)
    renamed = ok(
        owner.patch(url(f"/cycles/{s['cycle']['id']}"), json={"name": "Nightly", "environment": "prod"})
    )
    assert (renamed["name"], renamed["environment"]) == ("Nightly", "prod")
    assert owner.patch(url(f"/cycles/{s['cycle']['id']}"), json={"status": "closed"}).status_code == 422
    assert sorted(e["action"] for e in events(owner, "cycle")) == ["cycle.create", "cycle.update"]


def test_a_tester_records_results_but_does_not_create_cycles(owner, client_factory):
    s = run_seed(owner)
    add_member(owner, "tess@example.com", "tester")
    tess = client_factory()
    login(tess, "tess@example.com")
    p = s["product"]["id"]
    assert tess.post(url(f"/products/{p}/cycles"), json={"name": "R"}).status_code == 403
    ok(record(tess, s["cycle_case"]["id"], status="success"), 201)
