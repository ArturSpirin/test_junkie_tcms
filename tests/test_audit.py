"""The audit log names the person, the agent and the token behind every change, and feeds the outbox."""

from datetime import datetime

from sqlalchemy import select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.base import aware
from test_junkie_tcms.db.models import AuditEvent, Outbox
from tests import support
from tests.catalog_seed import make_product
from tests.support import add_member, login
from tests.test_consumers import ROSTER, FakeConsumer, approve


def _events(owner, **params):
    response = owner.get("/api/v1/orgs/acme/audit", params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _my_actor(owner):
    return owner.get("/api/v1/me").json()


@Suite(parameters=support.DATABASES)
class Audit:
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
    def test_cookie_change_names_the_person(self, suite_parameter):
        owner = self.env.owner
        me = _my_actor(owner)
        member = add_member(owner, "vic@example.com", "viewer")
        [event] = _events(owner, entity_type="user")
        assert event["action"] == "member.add"
        assert event["entity_id"] == member["user_id"]
        assert event["via"] == "ui"
        assert event["token_id"] is None
        assert event["on_behalf_of_user_id"] is None
        assert event["actor_id"] != member["actor_id"]
        actors = {a["user_id"]: a["actor_id"] for a in owner.get("/api/v1/orgs/acme/members").json()["items"]}
        assert event["actor_id"] == actors[me["user_id"]]
        assert event["changes"] == {"email": "vic@example.com", "role": "viewer"}

    @test()
    def test_agent_token_change_names_agent_token_and_owner(self, suite_parameter):
        owner = self.env.owner
        me = _my_actor(owner)
        agent = owner.post("/api/v1/orgs/acme/agents", json={"name": "bot", "role": "admin"}).json()
        created = owner.post(
            "/api/v1/orgs/acme/tokens",
            json={"name": "bot", "scopes": ["read", "admin"], "actor_id": agent["id"]},
        ).json()
        api = self.env.bearer(created["token"])
        assert api.patch("/api/v1/orgs/acme", json={"name": "Acme by bot"}).status_code == 200
        [event] = _events(owner, entity_type="org")
        assert event["action"] == "org.update"
        assert event["actor_id"] == agent["id"]
        assert event["token_id"] == created["id"]
        assert event["on_behalf_of_user_id"] == me["user_id"]
        assert event["via"] == "api"

    @test()
    def test_every_change_is_audited_with_an_outbox_row(self, suite_parameter):
        owner = self.env.owner
        app = self.env.app
        member = add_member(owner, "vic@example.com", "viewer")
        owner.patch(f"/api/v1/orgs/acme/members/{member['user_id']}", json={"role": "tester"})
        agent = owner.post("/api/v1/orgs/acme/agents", json={"name": "bot", "role": "viewer"}).json()
        owner.patch(f"/api/v1/orgs/acme/agents/{agent['id']}", json={"name": "bot2"})
        token = owner.post("/api/v1/orgs/acme/tokens", json={"name": "t", "scopes": ["read"]}).json()
        owner.delete(f"/api/v1/orgs/acme/tokens/{token['id']}")
        owner.post(f"/api/v1/orgs/acme/agents/{agent['id']}/disable")
        owner.delete(f"/api/v1/orgs/acme/members/{member['user_id']}")
        owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})

        expected = [
            "member.add",
            "member.update",
            "agent.create",
            "agent.update",
            "token.create",
            "token.revoke",
            "agent.disable",
            "member.remove",
            "org.update",
        ]
        assert sorted(e["action"] for e in _events(owner)) == sorted(expected)
        with app.state.sessionmaker() as db:
            events = {e.id: e.action for e in db.scalars(select(AuditEvent))}
            outbox = db.scalars(select(Outbox)).all()
        assert sorted(o.topic for o in outbox) == sorted(expected)
        assert {o.audit_event_id for o in outbox} == set(events)
        assert all(events[o.audit_event_id] == o.topic for o in outbox)

    @test()
    def test_failed_change_writes_nothing(self, suite_parameter):
        owner = self.env.owner
        app = self.env.app
        me = _my_actor(owner)
        owner.patch(f"/api/v1/orgs/acme/members/{me['user_id']}", json={"role": "admin"})
        with app.state.sessionmaker() as db:
            assert db.scalars(select(AuditEvent)).all() == []
            assert db.scalars(select(Outbox)).all() == []

    @test()
    def test_login_is_not_an_audit_event(self, suite_parameter):
        assert self.env.owner is not None  # signs in
        app = self.env.app
        with app.state.sessionmaker() as db:
            assert db.scalars(select(AuditEvent)).all() == []

    @test()
    def test_audit_filters(self, suite_parameter):
        owner = self.env.owner
        member = add_member(owner, "vic@example.com", "viewer")
        owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
        assert [e["action"] for e in _events(owner, entity_id=member["user_id"])] == ["member.add"]
        assert [e["action"] for e in _events(owner, entity_type="org")] == ["org.update"]
        assert _events(owner, actor_id="01NOTANACTOR0000000000000") == []

    @test()
    def test_audit_filters_via_action_until(self, suite_parameter):
        owner = self.env.owner
        app = self.env.app
        add_member(owner, "vic@example.com", "viewer")
        token = owner.post("/api/v1/orgs/acme/tokens", json={"name": "t", "scopes": ["read", "admin"]}).json()
        self.env.bearer(token["token"]).patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
        with app.state.sessionmaker() as db:
            times = {e.action: e.created_at for e in db.scalars(select(AuditEvent))}
        assert [e["action"] for e in _events(owner, via="api")] == ["org.update"]
        assert sorted(e["action"] for e in _events(owner, via="ui")) == ["member.add", "token.create"]
        assert _events(owner, via="mcp") == []
        assert [e["action"] for e in _events(owner, action="token.create")] == ["token.create"]
        assert _events(owner, action="token") == []
        # until is exclusive and since inclusive, so [t, t] is empty and [t, later) holds t's event.
        t = times["token.create"].isoformat()
        assert _events(owner, since=t, until=t) == []
        assert [e["action"] for e in _events(owner, until=t)] == ["member.add"]
        assert [e["action"] for e in _events(owner, since=t, via="ui")] == ["token.create"]
        assert _events(owner, via="api", action="member.add") == []
        combined = _events(owner, via="ui", action="member.add", until="2999-01-01T00:00:00Z")
        assert [e["action"] for e in combined] == ["member.add"]

    @test()
    def test_audit_filters_by_actor_kind(self, suite_parameter):
        owner = self.env.owner
        add_member(owner, "vic@example.com", "viewer")  # a member in the app
        token = owner.post("/api/v1/orgs/acme/tokens", json={"name": "t", "scopes": ["read", "admin"]}).json()
        self.env.bearer(token["token"]).patch("/api/v1/orgs/acme", json={"name": "By token"})
        agent = owner.post("/api/v1/orgs/acme/agents", json={"name": "bot", "role": "admin"}).json()
        agent_token = owner.post(
            "/api/v1/orgs/acme/tokens",
            json={"name": "bot", "scopes": ["read", "admin"], "actor_id": agent["id"]},
        ).json()
        self.env.bearer(agent_token["token"]).patch("/api/v1/orgs/acme", json={"name": "By bot"})
        fake = FakeConsumer(self.env)
        fake.start()
        approve(owner, fake.pairing["user_code"], "build-box", [make_product(owner)["id"]])
        fake.claim()
        assert fake.upload("web", ROSTER).status_code == 200

        by_kind = {kind: _events(owner, actor_kind=kind) for kind in ("user", "token", "agent", "consumer")}
        assert {e["action"] for e in by_kind["token"]} == {"org.update"}
        assert {e["token_id"] for e in by_kind["token"]} == {token["id"]}
        assert {e["action"] for e in by_kind["agent"]} == {"org.update"}
        assert {e["actor_id"] for e in by_kind["agent"]} == {agent["id"]}
        assert "consumer.inventory" in {e["action"] for e in by_kind["consumer"]}
        assert {e["actor_id"] for e in by_kind["consumer"]} == {by_kind["consumer"][0]["actor_id"]}
        assert {"member.add", "agent.create", "token.create"} <= {e["action"] for e in by_kind["user"]}
        assert all(e["token_id"] is None for e in by_kind["user"])
        # The four kinds split the log with no overlap and nothing left out.
        ids = [e["id"] for events in by_kind.values() for e in events]
        assert sorted(ids) == sorted(e["id"] for e in _events(owner))
        assert owner.get("/api/v1/orgs/acme/audit", params={"actor_kind": "robot"}).status_code == 422

    @test()
    def test_audit_q_matches_action_entity_and_actor_name(self, suite_parameter):
        owner = self.env.owner
        member = add_member(owner, "vic@example.com", "viewer")
        agent = owner.post("/api/v1/orgs/acme/agents", json={"name": "Nightly Bot", "role": "admin"}).json()
        agent_token = owner.post(
            "/api/v1/orgs/acme/tokens",
            json={"name": "bot", "scopes": ["read", "admin"], "actor_id": agent["id"]},
        ).json()
        self.env.bearer(agent_token["token"]).patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})

        assert {e["action"] for e in _events(owner, q="MEMBER.")} == {"member.add"}  # action, any case
        assert [e["action"] for e in _events(owner, q=member["user_id"])] == ["member.add"]  # entity id
        assert {e["action"] for e in _events(owner, q="nightly")} == {"org.update"}  # the actor's name
        assert _events(owner, q="%") == []  # wildcards are literal
        assert owner.get("/api/v1/orgs/acme/audit", params={"q": "x" * 201}).status_code == 422

    @test()
    def test_audit_retention_states_the_policy_and_the_oldest_row_kept(self, suite_parameter):
        owner = self.env.owner
        app = self.env.app
        empty = owner.get("/api/v1/orgs/acme/audit/retention")
        assert empty.status_code == 200, empty.text
        assert empty.json() == {"days": 90, "oldest_kept": None}
        add_member(owner, "vic@example.com", "viewer")
        owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
        with app.state.sessionmaker() as db:
            oldest = min(e.created_at for e in db.scalars(select(AuditEvent)))
        kept = owner.get("/api/v1/orgs/acme/audit/retention").json()["oldest_kept"]
        assert datetime.fromisoformat(kept.replace("Z", "+00:00")) == aware(oldest)
        viewer = self.env.client()
        login(viewer, "vic@example.com")
        assert viewer.get("/api/v1/orgs/acme/audit/retention").status_code == 403

    @test()
    def test_audit_rejects_an_unknown_via(self, suite_parameter):
        owner = self.env.owner
        assert owner.get("/api/v1/orgs/acme/audit", params={"via": "email"}).status_code == 422

    @test()
    def test_audit_is_per_org(self, suite_parameter):
        owner = self.env.owner
        owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
        other = self.env.client()
        login(other, "other@example.com")
        assert other.get("/api/v1/orgs/globex/audit").json()["items"] == []
        assert other.get("/api/v1/orgs/acme/audit").status_code == 404
