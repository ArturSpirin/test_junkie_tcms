"""A cycle runs the case version it pinned; later case edits don't reach it (T4)."""

from catalog_seed import events, ok, url
from execution_seed import cycle_cases, make_cycle, record, run_seed


def edit_steps(owner, case: dict, version: int = 1) -> dict:
    """Version 2: the first step reworded (same id), the second dropped, a new one added."""
    first = case["steps"][0]
    steps = [
        {"id": first["id"], "action": {"markdown": "Open the basket"}, "expected": {"markdown": "It opens"}},
        {"action": {"markdown": "Pay by voucher"}, "expected": {"markdown": "The order is paid"}},
    ]
    return ok(
        owner.patch(url(f"/cases/{case['key']}"), json={"steps": steps}, headers={"If-Match": f'"{version}"'})
    )


def test_a_case_edit_does_not_change_a_cycle_already_created(owner):
    s = run_seed(owner)
    v1_steps = s["cycle_case"]["steps"]
    edited = edit_steps(owner, s["case"])
    assert edited["current_version"] == 2

    [cc] = cycle_cases(owner, s["cycle"]["id"])
    assert (cc["case_version"], cc["current_version"]) == (1, 2)
    assert cc["steps"] == v1_steps
    assert cc["title"] == "Pay by card"

    # A cycle made after the edit pins version 2.
    later = make_cycle(owner, s["product"]["id"], case_ids=[s["case"]["id"]])
    [cc2] = cycle_cases(owner, later["id"])
    assert cc2["case_version"] == 2
    assert [st["id"] for st in cc2["steps"]] == [st["id"] for st in edited["steps"]]


def test_results_take_step_ids_of_the_pinned_version_only(owner):
    s = run_seed(owner)
    v1_dropped = s["case"]["steps"][1]["id"]
    edited = edit_steps(owner, s["case"])
    v2_only = edited["steps"][1]["id"]
    assert v2_only not in {st["id"] for st in s["case"]["steps"]}

    cc = s["cycle_case"]["id"]
    refused = record(owner, cc, status="success", steps=[{"step_id": v2_only, "status": "success"}])
    assert refused.status_code == 422, refused.text
    # The step version 2 dropped is still a step of the pinned version 1.
    ok(record(owner, cc, status="fail", steps=[{"step_id": v1_dropped, "status": "fail"}]), 201)


def test_refresh_version_repins_until_a_result_exists(owner):
    s = run_seed(owner)
    edit_steps(owner, s["case"])
    cc = s["cycle_case"]["id"]
    refreshed = ok(owner.post(url(f"/cycle-cases/{cc}/refresh-version")))
    assert refreshed["case_version"] == 2
    [event] = events(owner, "cycle_case")
    assert event["action"] == "cycle_case.refresh_version"

    ok(record(owner, cc, status="success"), 201)
    edit_steps(owner, {**s["case"], "steps": refreshed["steps"]}, version=2)
    again = owner.post(url(f"/cycle-cases/{cc}/refresh-version"))
    assert again.status_code == 409 and again.json()["code"] == "has_results"
    assert cycle_cases(owner, s["cycle"]["id"])[0]["case_version"] == 2


def test_an_archived_case_keeps_its_place_in_an_existing_cycle(owner):
    s = run_seed(owner)
    ok(owner.post(url(f"/cases/{s['case']['id']}/archive")))
    [cc] = cycle_cases(owner, s["cycle"]["id"])
    assert cc["case_version"] == 1
    ok(record(owner, cc["id"], status="success"), 201)
