"""Scoped, revocable API tokens."""

from datetime import UTC, datetime, timedelta

from conftest import add_member, bearer, login


def _create(client, org="acme", **body):
    body.setdefault("name", "ci")
    body.setdefault("scopes", ["read"])
    return client.post(f"/api/v1/orgs/{org}/tokens", json=body)


def test_token_is_shown_once_and_authenticates(owner, client_factory):
    response = _create(owner, scopes=["read", "admin"])
    assert response.status_code == 201
    created = response.json()
    assert created["token"].startswith("tjt_")
    listed = owner.get("/api/v1/orgs/acme/tokens").json()["items"]
    assert [t["id"] for t in listed] == [created["id"]]
    assert "token" not in listed[0]

    api = bearer(client_factory, created["token"])
    me = api.get("/api/v1/me").json()
    assert me["via"] == "api"
    assert me["token_id"] == created["id"]
    assert api.get("/api/v1/orgs/acme").status_code == 200


def test_bearer_needs_no_csrf(owner, client_factory):
    token = _create(owner, scopes=["admin"]).json()["token"]
    response = bearer(client_factory, token).patch("/api/v1/orgs/acme", json={"name": "Via API"})
    assert response.status_code == 200


def test_scope_limits_what_the_token_does(owner, client_factory):
    api = bearer(client_factory, _create(owner, scopes=["read"]).json()["token"])
    assert api.get("/api/v1/orgs/acme").status_code == 200
    assert api.patch("/api/v1/orgs/acme", json={"name": "Nope"}).status_code == 403
    assert api.get("/api/v1/orgs/acme/audit").status_code == 403


def test_revoked_token_is_401(owner, client_factory):
    created = _create(owner).json()
    api = bearer(client_factory, created["token"])
    assert api.get("/api/v1/me").status_code == 200
    assert owner.delete(f"/api/v1/orgs/acme/tokens/{created['id']}").status_code == 204
    assert api.get("/api/v1/me").status_code == 401


def test_expired_token_is_401(owner, client_factory):
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    api = bearer(client_factory, _create(owner, expires_at=past).json()["token"])
    assert api.get("/api/v1/me").status_code == 401


def test_naive_expiry_is_422(owner):
    assert _create(owner, expires_at="2030-01-01T00:00:00").status_code == 422


def test_bad_or_malformed_bearer_is_401(client_factory):
    assert bearer(client_factory, "tjt_notarealtoken").get("/api/v1/me").status_code == 401
    client = client_factory()
    client.headers["Authorization"] = "Basic abc"
    assert client.get("/api/v1/me").status_code == 401


def test_token_is_bound_to_its_org(owner, client_factory):
    api = bearer(client_factory, _create(owner).json()["token"])
    assert api.get("/api/v1/orgs/globex").status_code == 404


def test_unknown_scope_is_422(owner):
    assert _create(owner, scopes=["read", "root"]).status_code == 422


def test_product_ids_refused_until_t2(owner):
    assert _create(owner, product_ids=["p1"]).status_code == 422


def test_viewer_gets_own_read_token_but_nothing_above_role(owner, client_factory):
    add_member(owner, "vic@example.com", "viewer")
    viewer = client_factory()
    login(viewer, "vic@example.com")
    assert _create(viewer, scopes=["read"]).status_code == 201
    assert _create(viewer, scopes=["write:cases"]).status_code == 422


def test_viewer_cannot_make_tokens_for_others(owner, client_factory):
    add_member(owner, "vic@example.com", "viewer")
    viewer = client_factory()
    login(viewer, "vic@example.com")
    agents = owner.post("/api/v1/orgs/acme/agents", json={"name": "bot", "role": "viewer"}).json()
    assert _create(viewer, actor_id=agents["id"]).status_code == 403


def test_token_cannot_mint_scopes_it_lacks(owner, client_factory):
    api = bearer(client_factory, _create(owner, scopes=["read", "tokens:self"]).json()["token"])
    assert _create(api, scopes=["read"]).status_code == 201
    assert _create(api, scopes=["admin"]).status_code == 422


def test_viewer_sees_only_own_tokens(owner, client_factory):
    _create(owner, name="owner-token")
    add_member(owner, "vic@example.com", "viewer")
    viewer = client_factory()
    login(viewer, "vic@example.com")
    _create(viewer, name="viewer-token")
    assert [t["name"] for t in viewer.get("/api/v1/orgs/acme/tokens").json()["items"]] == ["viewer-token"]
