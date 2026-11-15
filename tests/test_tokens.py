"""Scoped, revocable API tokens."""

from datetime import UTC, datetime, timedelta

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.support import add_member, login


def _create(client, org="acme", **body):
    body.setdefault("name", "ci")
    body.setdefault("scopes", ["read"])
    return client.post(f"/api/v1/orgs/{org}/tokens", json=body)


@Suite(parameters=support.DATABASES)
class Tokens:
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
    def test_token_is_shown_once_and_authenticates(self, suite_parameter):
        owner = self.env.owner
        response = _create(owner, scopes=["read", "admin"])
        assert response.status_code == 201
        created = response.json()
        assert created["token"].startswith("tjt_")
        listed = owner.get("/api/v1/orgs/acme/tokens").json()["items"]
        assert [t["id"] for t in listed] == [created["id"]]
        assert "token" not in listed[0]

        api = self.env.bearer(created["token"])
        me = api.get("/api/v1/me").json()
        assert me["via"] == "api"
        assert me["token_id"] == created["id"]
        assert api.get("/api/v1/orgs/acme").status_code == 200

    @test()
    def test_bearer_needs_no_csrf(self, suite_parameter):
        owner = self.env.owner
        token = _create(owner, scopes=["admin"]).json()["token"]
        response = self.env.bearer(token).patch("/api/v1/orgs/acme", json={"name": "Via API"})
        assert response.status_code == 200

    @test()
    def test_scope_limits_what_the_token_does(self, suite_parameter):
        owner = self.env.owner
        api = self.env.bearer(_create(owner, scopes=["read"]).json()["token"])
        assert api.get("/api/v1/orgs/acme").status_code == 200
        assert api.patch("/api/v1/orgs/acme", json={"name": "Nope"}).status_code == 403
        assert api.get("/api/v1/orgs/acme/audit").status_code == 403

    @test()
    def test_revoked_token_is_401(self, suite_parameter):
        owner = self.env.owner
        created = _create(owner).json()
        api = self.env.bearer(created["token"])
        assert api.get("/api/v1/me").status_code == 200
        assert owner.delete(f"/api/v1/orgs/acme/tokens/{created['id']}").status_code == 204
        assert api.get("/api/v1/me").status_code == 401

    @test()
    def test_expired_token_is_401(self, suite_parameter):
        owner = self.env.owner
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        api = self.env.bearer(_create(owner, expires_at=past).json()["token"])
        assert api.get("/api/v1/me").status_code == 401

    @test()
    def test_naive_expiry_is_422(self, suite_parameter):
        owner = self.env.owner
        assert _create(owner, expires_at="2030-01-01T00:00:00").status_code == 422

    @test()
    def test_bad_or_malformed_bearer_is_401(self, suite_parameter):
        assert self.env.bearer("tjt_notarealtoken").get("/api/v1/me").status_code == 401
        client = self.env.client()
        client.headers["Authorization"] = "Basic abc"
        assert client.get("/api/v1/me").status_code == 401

    @test()
    def test_token_is_bound_to_its_org(self, suite_parameter):
        owner = self.env.owner
        api = self.env.bearer(_create(owner).json()["token"])
        assert api.get("/api/v1/orgs/globex").status_code == 404

    @test()
    def test_unknown_scope_is_422(self, suite_parameter):
        owner = self.env.owner
        assert _create(owner, scopes=["read", "root"]).status_code == 422

    @test()
    def test_product_ids_must_be_products_of_the_org(self, suite_parameter):
        owner = self.env.owner
        pay = owner.post("/api/v1/orgs/acme/products", json={"key": "PAY", "name": "Pay"}).json()["id"]
        created = _create(owner, product_ids=[pay])
        assert created.status_code == 201
        assert created.json()["product_ids"] == [pay]
        assert _create(owner, product_ids=["p1"]).status_code == 422
        globex = self.env.client()
        login(globex, "other@example.com")
        theirs = globex.post("/api/v1/orgs/globex/products", json={"key": "GLO", "name": "G"}).json()["id"]
        assert _create(owner, product_ids=[theirs]).status_code == 422

    @test()
    def test_viewer_gets_own_read_token_but_nothing_above_role(self, suite_parameter):
        owner = self.env.owner
        add_member(owner, "vic@example.com", "viewer")
        viewer = self.env.client()
        login(viewer, "vic@example.com")
        assert _create(viewer, scopes=["read"]).status_code == 201
        assert _create(viewer, scopes=["write:cases"]).status_code == 422

    @test()
    def test_viewer_cannot_make_tokens_for_others(self, suite_parameter):
        owner = self.env.owner
        add_member(owner, "vic@example.com", "viewer")
        viewer = self.env.client()
        login(viewer, "vic@example.com")
        agents = owner.post("/api/v1/orgs/acme/agents", json={"name": "bot", "role": "viewer"}).json()
        assert _create(viewer, actor_id=agents["id"]).status_code == 403

    @test()
    def test_token_cannot_mint_scopes_it_lacks(self, suite_parameter):
        owner = self.env.owner
        api = self.env.bearer(_create(owner, scopes=["read", "tokens:self"]).json()["token"])
        assert _create(api, scopes=["read"]).status_code == 201
        assert _create(api, scopes=["admin"]).status_code == 422

    @test()
    def test_viewer_sees_only_own_tokens(self, suite_parameter):
        owner = self.env.owner
        _create(owner, name="owner-token")
        add_member(owner, "vic@example.com", "viewer")
        viewer = self.env.client()
        login(viewer, "vic@example.com")
        _create(viewer, name="viewer-token")
        assert [t["name"] for t in viewer.get("/api/v1/orgs/acme/tokens").json()["items"]] == ["viewer-token"]
