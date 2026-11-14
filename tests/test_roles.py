"""Membership roles, the owner rules, and agents clamped to their owner's role."""

import pytest
from conftest import add_member, bearer, login

from test_junkie_tcms.auth.scopes import ROLE_SCOPES, lower_role


def test_role_scopes_are_nested():
    order = ["viewer", "tester", "editor", "admin", "owner"]
    for lower, higher in zip(order, order[1:], strict=False):
        assert ROLE_SCOPES[lower] <= ROLE_SCOPES[higher]
    assert ROLE_SCOPES["viewer"] == {"read", "tokens:self"}
    assert lower_role("admin", "tester") == "tester"
    assert lower_role("viewer", None) is None


@pytest.mark.parametrize(
    ("role", "can_admin", "can_audit"),
    [("viewer", False, False), ("editor", False, False), ("admin", True, True)],
)
def test_member_role_decides_access(owner, client_factory, role, can_admin, can_audit):
    add_member(owner, f"{role}@example.com", role)
    member = client_factory()
    login(member, f"{role}@example.com")
    assert member.get("/api/v1/orgs/acme").status_code == 200
    patched = member.patch("/api/v1/orgs/acme", json={"name": "Renamed"})
    assert patched.status_code == (200 if can_admin else 403)
    assert member.get("/api/v1/orgs/acme/audit").status_code == (200 if can_audit else 403)


def test_only_an_owner_grants_owner(owner, client_factory):
    add_member(owner, "ada@example.com", "admin")
    admin = client_factory()
    login(admin, "ada@example.com")
    response = admin.post(
        "/api/v1/orgs/acme/members", json={"email": "x@example.com", "name": "X", "role": "owner"}
    )
    assert response.status_code == 403


def test_last_owner_stays(owner):
    me = owner.get("/api/v1/me").json()
    assert (
        owner.patch(f"/api/v1/orgs/acme/members/{me['user_id']}", json={"role": "admin"}).status_code == 409
    )
    assert owner.delete(f"/api/v1/orgs/acme/members/{me['user_id']}").status_code == 409


def test_member_readd_is_409(owner):
    add_member(owner, "vic@example.com", "viewer")
    response = owner.post(
        "/api/v1/orgs/acme/members", json={"email": "vic@example.com", "name": "Vic", "role": "viewer"}
    )
    assert response.status_code == 409


def test_removed_member_loses_the_org(owner, client_factory):
    member = add_member(owner, "vic@example.com", "viewer")
    viewer = client_factory()
    login(viewer, "vic@example.com")
    assert viewer.get("/api/v1/orgs/acme").status_code == 200
    assert owner.delete(f"/api/v1/orgs/acme/members/{member['user_id']}").status_code == 204
    assert viewer.get("/api/v1/orgs/acme").status_code == 404


def test_agent_role_cannot_exceed_owner_at_creation(owner, client_factory):
    tester = add_member(owner, "tess@example.com", "tester")
    response = owner.post(
        "/api/v1/orgs/acme/agents",
        json={"name": "bot", "role": "editor", "owner_user_id": tester["user_id"]},
    )
    assert response.status_code == 422


def _agent_token(owner, owner_user_id, role="editor", scopes=("read", "write:cases")):
    agent = owner.post(
        "/api/v1/orgs/acme/agents", json={"name": "bot", "role": role, "owner_user_id": owner_user_id}
    ).json()
    created = owner.post(
        "/api/v1/orgs/acme/tokens", json={"name": "bot", "scopes": list(scopes), "actor_id": agent["id"]}
    )
    assert created.status_code == 201, created.text
    return agent, created.json()["token"]


def test_agent_is_clamped_when_owner_is_demoted(owner, client_factory):
    ed = add_member(owner, "ed@example.com", "editor")
    _, token = _agent_token(
        owner, ed["user_id"], role="editor", scopes=["read", "tokens:self", "write:cases"]
    )
    api = bearer(client_factory, token)
    # write:cases is checked by the token-mint rule: the agent may mint it while its owner is an editor.
    assert (
        api.post("/api/v1/orgs/acme/tokens", json={"name": "t", "scopes": ["write:cases"]}).status_code == 201
    )
    owner.patch(f"/api/v1/orgs/acme/members/{ed['user_id']}", json={"role": "viewer"})
    assert (
        api.post("/api/v1/orgs/acme/tokens", json={"name": "t", "scopes": ["write:cases"]}).status_code == 422
    )
    assert api.get("/api/v1/orgs/acme").status_code == 200


def test_agent_loses_the_org_when_owner_is_removed(owner, client_factory):
    ed = add_member(owner, "ed@example.com", "editor")
    _, token = _agent_token(owner, ed["user_id"])
    api = bearer(client_factory, token)
    assert api.get("/api/v1/orgs/acme").status_code == 200
    owner.delete(f"/api/v1/orgs/acme/members/{ed['user_id']}")
    assert api.get("/api/v1/orgs/acme").status_code == 404


def test_disabled_agent_loses_the_org(owner, client_factory):
    me = owner.get("/api/v1/me").json()
    agent, token = _agent_token(owner, me["user_id"])
    api = bearer(client_factory, token)
    assert owner.post(f"/api/v1/orgs/acme/agents/{agent['id']}/disable").status_code == 200
    # A disabled actor's tokens stop authenticating at all.
    assert api.get("/api/v1/me").status_code == 401
