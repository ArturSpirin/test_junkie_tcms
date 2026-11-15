"""Cookie sessions with double-submit CSRF."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.auth.sessions import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from tests import support
from tests.support import OWNER_EMAIL, PASSWORD, login


@Suite(parameters=support.DATABASES)
class SessionCsrf:
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
    def test_login_sets_session_and_csrf_cookies(self, suite_parameter):
        client = self.env.client()
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

    @test()
    def test_wrong_password_is_401(self, suite_parameter):
        response = self.env.client().post(
            "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "nope-nope"}
        )
        assert response.status_code == 401
        assert SESSION_COOKIE not in response.cookies

    @test()
    def test_unknown_email_still_runs_argon2(self, suite_parameter):
        from test_junkie_tcms.auth import passwords

        client = self.env.client()
        calls = []
        real = passwords._hasher

        class Spy:
            def verify(self, h, p):
                calls.append(h)
                return real.verify(h, p)

        self.env.patch(passwords, "_hasher", Spy())
        response = client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "nope-nope"}
        )
        assert response.status_code == 401
        assert calls == [passwords._DUMMY_HASH]

    @test()
    def test_no_credentials_is_401(self, suite_parameter):
        assert self.env.client().get("/api/v1/me").status_code == 401

    @test()
    def test_safe_request_needs_no_csrf(self, suite_parameter):
        client = self.env.client()
        login(client)
        del client.headers[CSRF_HEADER]
        assert client.get("/api/v1/orgs/acme").status_code == 200

    @test()
    def test_unsafe_request_without_csrf_header_is_403(self, suite_parameter):
        client = self.env.client()
        login(client)
        del client.headers[CSRF_HEADER]
        response = client.patch("/api/v1/orgs/acme", json={"name": "Hijacked"})
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    @test()
    def test_unsafe_request_with_wrong_csrf_is_403(self, suite_parameter):
        client = self.env.client()
        login(client)
        client.headers[CSRF_HEADER] = "not-the-token"
        assert client.patch("/api/v1/orgs/acme", json={"name": "Hijacked"}).status_code == 403

    @test()
    def test_unsafe_request_with_csrf_passes(self, suite_parameter):
        response = self.env.owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
        assert response.status_code == 200
        assert response.json()["name"] == "Acme Inc"

    @test()
    def test_csrf_from_another_session_is_403(self, suite_parameter):
        first, second = self.env.client(), self.env.client()
        login(first)
        login(second)
        first.headers[CSRF_HEADER] = second.cookies[CSRF_COOKIE]
        first.cookies.set(CSRF_COOKIE, second.cookies[CSRF_COOKIE])
        assert first.patch("/api/v1/orgs/acme", json={"name": "Mixed"}).status_code == 403

    @test()
    def test_logout_ends_the_session(self, suite_parameter):
        owner = self.env.owner
        assert owner.get("/api/v1/me").status_code == 200
        stolen = owner.cookies[SESSION_COOKIE]
        assert owner.post("/api/v1/auth/logout").status_code == 204
        owner.cookies.set(SESSION_COOKIE, stolen)
        assert owner.get("/api/v1/me").status_code == 401

    @test()
    def test_other_org_is_404(self, suite_parameter):
        owner = self.env.owner
        assert owner.get("/api/v1/orgs/globex").status_code == 404
        assert owner.get("/api/v1/orgs/nope").status_code == 404
