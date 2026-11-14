"""The audit log names the person, the agent and the token behind every change, and feeds the outbox."""

from conftest import add_member, bearer, login
from sqlalchemy import select

from test_junkie_tcms.db.models import AuditEvent, Outbox


def _events(owner, **params):
    response = owner.get("/api/v1/orgs/acme/audit", params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _my_actor(owner):
    return owner.get("/api/v1/me").json()


def test_cookie_change_names_the_person(owner):
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


def test_agent_token_change_names_agent_token_and_owner(owner, client_factory):
    me = _my_actor(owner)
    agent = owner.post("/api/v1/orgs/acme/agents", json={"name": "bot", "role": "admin"}).json()
    created = owner.post(
        "/api/v1/orgs/acme/tokens", json={"name": "bot", "scopes": ["read", "admin"], "actor_id": agent["id"]}
    ).json()
    api = bearer(client_factory, created["token"])
    assert api.patch("/api/v1/orgs/acme", json={"name": "Acme by bot"}).status_code == 200
    [event] = _events(owner, entity_type="org")
    assert event["action"] == "org.update"
    assert event["actor_id"] == agent["id"]
    assert event["token_id"] == created["id"]
    assert event["on_behalf_of_user_id"] == me["user_id"]
    assert event["via"] == "api"


def test_every_change_is_audited_with_an_outbox_row(owner, app):
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


def test_failed_change_writes_nothing(owner, app):
    me = _my_actor(owner)
    owner.patch(f"/api/v1/orgs/acme/members/{me['user_id']}", json={"role": "admin"})
    with app.state.sessionmaker() as db:
        assert db.scalars(select(AuditEvent)).all() == []
        assert db.scalars(select(Outbox)).all() == []


def test_login_is_not_an_audit_event(owner, app):
    with app.state.sessionmaker() as db:
        assert db.scalars(select(AuditEvent)).all() == []


def test_audit_filters(owner):
    member = add_member(owner, "vic@example.com", "viewer")
    owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
    assert [e["action"] for e in _events(owner, entity_id=member["user_id"])] == ["member.add"]
    assert [e["action"] for e in _events(owner, entity_type="org")] == ["org.update"]
    assert _events(owner, actor_id="01NOTANACTOR0000000000000") == []


def test_audit_is_per_org(owner, client_factory):
    owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
    other = client_factory()
    login(other, "other@example.com")
    assert other.get("/api/v1/orgs/globex/audit").json()["items"] == []
    assert other.get("/api/v1/orgs/acme/audit").status_code == 404
