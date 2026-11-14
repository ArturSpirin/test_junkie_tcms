"""Execution rows stay inside their org, and inside a token's products (T4)."""

from catalog_seed import ok, url
from conftest import bearer, login
from execution_seed import record, run_seed


def seeded(owner) -> dict:
    s = run_seed(owner)
    p = s["product"]["id"]
    shot = ok(
        owner.post(
            url(f"/products/{p}/attachments"),
            params={"filename": "a.png"},
            content=b"png",
            headers={"Content-Type": "image/png"},
        ),
        201,
    )
    result = ok(record(owner, s["cycle_case"]["id"], status="fail", attachment_ids=[shot["id"]]), 201)
    batch = ok(owner.post(url(f"/releases/{s['release']['id']}/cycles/bulk"), json={}), 201)
    return {**s, "attachment": shot, "result": result, "batch": batch}


def reads(s: dict) -> list[tuple[str, str, dict | None]]:
    cycle, cc = s["cycle"]["id"], s["cycle_case"]["id"]
    return [
        ("GET", f"/cycles/{cycle}", None),
        ("GET", f"/cycles/{cycle}/cases", None),
        ("GET", f"/cycle-cases/{cc}/results", None),
        ("GET", f"/attachments/{s['attachment']['id']}", None),
        ("GET", f"/cycle-batches/{s['batch']['id']}", None),
        ("PATCH", f"/cycles/{cycle}", {"name": "X"}),
        ("POST", f"/cycles/{cycle}/close", None),
        ("POST", f"/cycles/{cycle}/cases", {"case_ids": [s["case"]["id"]]}),
        ("POST", f"/cycle-cases/{cc}/results", {"status": "success"}),
        ("POST", f"/cycle-cases/{cc}/refresh-version", None),
        ("POST", f"/cycles/{cycle}/results/bulk", {"items": [{"case_key": "PAY-1", "status": "success"}]}),
        ("POST", f"/releases/{s['release']['id']}/cycles/bulk", {}),
    ]


def test_another_org_gets_404_through_its_own_path(owner, client_factory):
    s = seeded(owner)
    gus = client_factory()
    login(gus, "other@example.com")
    for method, path, body in reads(s):
        response = gus.request(method, url(path, "globex"), json=body)
        assert response.status_code == 404, (path, response.text)


def test_another_org_cannot_use_acme_paths(owner, client_factory):
    s = seeded(owner)
    gus = client_factory()
    login(gus, "other@example.com")
    for method, path, body in reads(s):
        assert gus.request(method, url(path), json=body).status_code in (403, 404), path


def test_a_token_limited_to_another_product_sees_none_of_it(owner, client_factory):
    s = seeded(owner)
    other = run_seed(owner, "OPS")
    scopes = ["read", "write:planning", "write:execution"]
    body = {"name": "ops only", "scopes": scopes, "product_ids": [other["product"]["id"]]}
    ops = bearer(client_factory, ok(owner.post(url("/tokens"), json=body), 201)["token"])
    for method, path, body in reads(s):
        assert ops.request(method, url(path), json=body).status_code == 404, path
    p = s["product"]["id"]
    assert ops.get(url(f"/products/{p}/cycles")).status_code == 404
    upload = ops.post(url(f"/products/{p}/attachments"), params={"filename": "a.png"}, content=b"x")
    assert upload.status_code == 404
    # Its own product works.
    ok(ops.get(url(f"/cycles/{other['cycle']['id']}")))
    # And nothing in acme changed.
    assert ok(owner.get(url(f"/cycles/{s['cycle']['id']}")))["status"] == "open"
    assert len(ok(owner.get(url(f"/cycle-cases/{s['cycle_case']['id']}/results")))["items"]) == 1
