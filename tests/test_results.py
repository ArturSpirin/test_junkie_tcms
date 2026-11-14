"""Results: append-only attempts with per-step status, evidence, defects and where they came from (T4)."""

from catalog_seed import events, ok, url
from conftest import bearer
from execution_seed import cycle_cases, make_case, make_cycle, record, run_seed


def upload(client, product: str, content: bytes = b"\x89PNG shot", name: str = "shot.png") -> dict:
    response = client.post(
        url(f"/products/{product}/attachments"),
        params={"filename": name},
        content=content,
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def token(owner, *scopes: str, **body) -> str:
    body = {"name": "ci", "scopes": list(scopes), **body}
    return ok(owner.post(url("/tokens"), json=body), 201)["token"]


def test_a_result_stores_per_step_status_evidence_and_defects(owner):
    s = run_seed(owner)
    shot = upload(owner, s["product"]["id"])
    log = upload(owner, s["product"]["id"], b"log line", "run.log")
    first, second = (st["id"] for st in s["case"]["steps"])
    body = {
        "status": "fail",
        "comment": {"markdown": "Card declined"},
        "duration_ms": 1200,
        "steps": [
            {"step_id": first, "status": "success"},
            {
                "step_id": second,
                "status": "fail",
                "actual": {"markdown": "Error 500"},
                "attachment_ids": [shot["id"]],
            },
        ],
        "attachment_ids": [log["id"]],
        "defects": [{"url": "https://issues.example.com/BUG-7", "key": "BUG-7"}],
    }
    result = ok(record(owner, s["cycle_case"]["id"], **body), 201)
    assert (result["attempt"], result["status"], result["via"], result["duration_ms"]) == (
        1,
        "fail",
        "ui",
        1200,
    )
    assert result["comment"].strip() == "Card declined"
    assert [(st["step_id"], st["status"]) for st in result["steps"]] == [(first, "success"), (second, "fail")]
    assert result["steps"][1]["actual"].strip() == "Error 500"
    assert result["steps"][1]["attachment_ids"] == [shot["id"]]
    assert result["attachment_ids"] == [log["id"]]
    assert result["defects"] == [{"url": "https://issues.example.com/BUG-7", "key": "BUG-7"}]

    [listed] = ok(owner.get(url(f"/cycle-cases/{s['cycle_case']['id']}/results")))["items"]
    assert listed == result
    [cc] = cycle_cases(owner, s["cycle"]["id"])
    assert cc["status"] == "fail" and cc["last_result_at"] is not None
    [event] = events(owner, "result")
    assert event["action"] == "result.create"


def test_a_retest_is_the_next_attempt_and_moves_the_counts(owner):
    s = run_seed(owner)
    cc = s["cycle_case"]["id"]
    ok(record(owner, cc, status="fail"), 201)
    second = ok(record(owner, cc, status="success"), 201)
    assert second["attempt"] == 2
    attempts = ok(owner.get(url(f"/cycle-cases/{cc}/results")))["items"]
    assert [(r["attempt"], r["status"]) for r in attempts] == [(1, "fail"), (2, "success")]
    counts = ok(owner.get(url(f"/cycles/{s['cycle']['id']}")))["counts"]
    assert counts == {"untested": 0, "success": 1, "fail": 0, "error": 0, "ignore": 0, "skip": 0, "cancel": 0}


def test_a_skip_needs_a_reason(owner):
    s = run_seed(owner)
    cc = s["cycle_case"]["id"]
    refused = record(owner, cc, status="skip")
    assert refused.status_code == 422 and refused.json()["code"] == "skip_needs_reason"
    blank = record(owner, cc, status="skip", comment={"markdown": "  "})
    assert blank.status_code == 422
    ok(record(owner, cc, status="skip", comment={"markdown": "Blocked by BUG-7"}), 201)


def test_bad_steps_statuses_and_attachments_are_refused(owner):
    s = run_seed(owner)
    cc = s["cycle_case"]["id"]
    step = s["case"]["steps"][0]["id"]
    assert record(owner, cc, status="untested").status_code == 422
    assert record(owner, cc, status="passed").status_code == 422
    assert record(owner, cc, status="fail", steps=[{"step_id": "nope", "status": "fail"}]).status_code == 422
    twice = [{"step_id": step, "status": "fail"}, {"step_id": step, "status": "success"}]
    assert record(owner, cc, status="fail", steps=twice).status_code == 422
    assert record(owner, cc, status="fail", steps=[{"step_id": step, "status": "ignore"}]).status_code == 422
    assert record(owner, cc, status="fail", attachment_ids=["nope"]).status_code == 422
    assert ok(owner.get(url(f"/cycle-cases/{cc}/results")))["items"] == []


def test_an_attachment_of_another_product_is_refused(owner):
    s = run_seed(owner)
    other = run_seed(owner, "OPS")
    elsewhere = upload(owner, other["product"]["id"])
    refused = record(owner, s["cycle_case"]["id"], status="fail", attachment_ids=[elsewhere["id"]])
    assert refused.status_code == 422, refused.text


def test_via_tells_api_mcp_and_ui_apart(owner, client_factory):
    s = run_seed(owner)
    cc = s["cycle_case"]["id"]
    bot = bearer(client_factory, token(owner, "read", "write:execution"))
    assert ok(record(bot, cc, status="success"), 201)["via"] == "api"
    mcp = bot.post(
        url(f"/cycle-cases/{cc}/results"), json={"status": "success"}, headers={"X-TCMS-Via": "mcp"}
    )
    assert ok(mcp, 201)["via"] == "mcp"
    # The label means nothing on a cookie session.
    ui = owner.post(
        url(f"/cycle-cases/{cc}/results"), json={"status": "success"}, headers={"X-TCMS-Via": "mcp"}
    )
    assert ok(ui, 201)["via"] == "ui"


def test_a_token_without_write_execution_cannot_record(owner, client_factory):
    s = run_seed(owner)
    reader = bearer(client_factory, token(owner, "read"))
    assert record(reader, s["cycle_case"]["id"], status="success").status_code == 403


def test_bulk_results_match_by_case_key_or_automation_ref(owner):
    s = run_seed(owner)
    p = s["product"]["id"]
    auto = make_case(owner, p, s["child"]["id"], "Automated", automation_ref="tests/test_pay.py::test_card")
    cycle = s["cycle"]["id"]
    ok(owner.post(url(f"/cycles/{cycle}/cases"), json={"case_ids": [auto["id"]]}))
    items = [
        {"case_key": "pay-1", "status": "success"},
        {"automation_ref": "tests/test_pay.py::test_card", "status": "fail", "comment": "Timeout"},
        {"case_key": "PAY-99", "status": "success"},
        {"automation_ref": "tests/missing.py::test_x", "status": "skip"},
    ]
    out = ok(owner.post(url(f"/cycles/{cycle}/results/bulk"), json={"items": items}), 201)
    assert [(r["index"], r["attempt"]) for r in out["created"]] == [(0, 1), (1, 1)]
    assert [u["index"] for u in out["unmatched"]] == [2, 3]
    statuses = {c["key"]: c["status"] for c in cycle_cases(owner, cycle)}
    assert statuses == {"PAY-1": "success", "PAY-2": "fail"}
    neither = owner.post(url(f"/cycles/{cycle}/results/bulk"), json={"items": [{"status": "success"}]})
    assert neither.status_code == 422


def test_results_are_never_edited(owner):
    s = run_seed(owner)
    result = ok(record(owner, s["cycle_case"]["id"], status="fail"), 201)
    path = url(f"/cycle-cases/{s['cycle_case']['id']}/results/{result['id']}")
    assert owner.patch(path, json={"status": "success"}).status_code in (404, 405)
    assert owner.delete(path).status_code in (404, 405)


def test_an_empty_cycle_has_zero_counts(owner):
    s = run_seed(owner)
    empty = make_cycle(owner, s["product"]["id"])
    assert set(empty["counts"].values()) == {0}
