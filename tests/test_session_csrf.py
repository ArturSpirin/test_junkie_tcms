"""Cookie sessions with double-submit CSRF."""

from conftest import OWNER_EMAIL, PASSWORD, login

from test_junkie_tcms.auth.sessions import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE


def test_login_sets_session_and_csrf_cookies(client_factory):
    client = client_factory()
    response = client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["via"] == "ui"
    assert body["email"] == OWNER_EMAIL
    assert [o["slug"] for o in body["orgs"]] == ["acme"]
    assert body["orgs"][0]["role"] == "owner"
    cookies = response.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith(f"{SESSION_COOKIE}="))
    csrf = next(c for c in cookies if c.startswith(f"{CSRF_COOKIE}="))
    assert "httponly" in session.lower()
    assert "httponly" not in csrf.lower()


def test_wrong_password_is_401(client_factory):
    response = client_factory().post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "nope-nope"}
    )
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_no_credentials_is_401(client_factory):
    assert client_factory().get("/api/v1/me").status_code == 401


def test_safe_request_needs_no_csrf(client_factory):
    client = client_factory()
    login(client)
    del client.headers[CSRF_HEADER]
    assert client.get("/api/v1/orgs/acme").status_code == 200


def test_unsafe_request_without_csrf_header_is_403(client_factory):
    client = client_factory()
    login(client)
    del client.headers[CSRF_HEADER]
    response = client.patch("/api/v1/orgs/acme", json={"name": "Hijacked"})
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_unsafe_request_with_wrong_csrf_is_403(client_factory):
    client = client_factory()
    login(client)
    client.headers[CSRF_HEADER] = "not-the-token"
    assert client.patch("/api/v1/orgs/acme", json={"name": "Hijacked"}).status_code == 403


def test_unsafe_request_with_csrf_passes(owner):
    response = owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
    assert response.status_code == 200
    assert response.json()["name"] == "Acme Inc"


def test_csrf_from_another_session_is_403(client_factory):
    first, second = client_factory(), client_factory()
    login(first)
    login(second)
    first.headers[CSRF_HEADER] = second.cookies[CSRF_COOKIE]
    first.cookies.set(CSRF_COOKIE, second.cookies[CSRF_COOKIE])
    assert first.patch("/api/v1/orgs/acme", json={"name": "Mixed"}).status_code == 403


def test_logout_ends_the_session(owner):
    assert owner.get("/api/v1/me").status_code == 200
    stolen = owner.cookies[SESSION_COOKIE]
    assert owner.post("/api/v1/auth/logout").status_code == 204
    owner.cookies.set(SESSION_COOKIE, stolen)
    assert owner.get("/api/v1/me").status_code == 401


def test_other_org_is_404(owner):
    assert owner.get("/api/v1/orgs/globex").status_code == 404
    assert owner.get("/api/v1/orgs/nope").status_code == 404
