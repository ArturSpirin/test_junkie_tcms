"""Invites: an admin invites an email for 7 days; the token is shown once, stored hashed, and works once."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import add_member, bearer, login
from sqlalchemy import select, update

from test_junkie_tcms.auth.tokens import token_hash
from test_junkie_tcms.db.models import Invite

INVITES = "/api/v1/orgs/acme/invites"
ACCEPT = "/api/v1/invites:accept"
INVITEE = "ivy@example.com"


def _invite(owner, email=INVITEE, role="tester"):
    response = owner.post(INVITES, json={"email": email, "role": role})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def globex(client_factory):
    client = client_factory()
    login(client, "other@example.com")
    return client


@pytest.fixture
def invitee(globex, client_factory):
    """A signed-in user with an account (a Globex member) who isn't in Acme yet."""
    add_member(globex, INVITEE, "viewer", org="globex")
    client = client_factory()
    login(client, INVITEE)
    return client


def _actions(owner, entity_id):
    response = owner.get("/api/v1/orgs/acme/audit", params={"entity_type": "invite", "entity_id": entity_id})
    assert response.status_code == 200, response.text
    return [(e["action"], e["via"]) for e in response.json()["items"]]


def test_token_is_shown_once_and_stored_hashed(owner, app):
    created = _invite(owner)
    assert created["token"].startswith("tji_")
    assert created["status"] == "pending"
    created_at = datetime.fromisoformat(created["created_at"])
    assert datetime.fromisoformat(created["expires_at"]) - created_at == timedelta(days=7)
    [listed] = owner.get(INVITES).json()["items"]
    assert listed["id"] == created["id"]
    assert "token" not in listed
    with app.state.sessionmaker() as db:
        row = db.get(Invite, created["id"])
        assert row.token_hash == token_hash(created["token"])
        assert created["token"] not in {row.token_hash, row.email}
    assert _actions(owner, created["id"]) == [("invite.create", "ui")]


def test_below_admin_cannot_invite_and_admin_cannot_invite_an_owner(owner, client_factory):
    add_member(owner, "tess@example.com", "tester")
    add_member(owner, "ada@example.com", "admin")
    tester, admin = client_factory(), client_factory()
    login(tester, "tess@example.com")
    login(admin, "ada@example.com")
    assert tester.post(INVITES, json={"email": INVITEE, "role": "viewer"}).status_code == 403
    assert tester.get(INVITES).status_code == 403
    assert admin.post(INVITES, json={"email": INVITEE, "role": "owner"}).status_code == 403
    assert admin.post(INVITES, json={"email": INVITEE, "role": "admin"}).status_code == 201


def test_member_or_pending_invite_conflicts(owner):
    add_member(owner, "vic@example.com", "viewer")
    assert owner.post(INVITES, json={"email": "Vic@Example.com", "role": "tester"}).status_code == 409
    _invite(owner)
    assert owner.post(INVITES, json={"email": INVITEE, "role": "viewer"}).status_code == 409


def test_accept_joins_the_org_once(owner, invitee):
    created = _invite(owner, role="tester")
    response = invitee.post(ACCEPT, json={"token": created["token"]})
    assert response.status_code == 200, response.text
    member = response.json()
    assert (member["email"], member["role"]) == (INVITEE, "tester")
    assert invitee.get("/api/v1/orgs/acme/members").status_code == 200
    [row] = owner.get(INVITES, params={"status": "accepted"}).json()["items"]
    assert row["accepted_user_id"] == member["user_id"]
    assert owner.get(INVITES).json()["items"] == []
    used = invitee.post(ACCEPT, json={"token": created["token"]})
    assert (used.status_code, used.json()["detail"]) == (410, "Invite already used")
    assert sorted(_actions(owner, created["id"])) == [("invite.accept", "ui"), ("invite.create", "ui")]


def test_accept_reinstates_a_removed_member(owner, client_factory):
    vic = add_member(owner, "vic@example.com", "viewer")
    assert owner.delete(f"/api/v1/orgs/acme/members/{vic['user_id']}").status_code == 204
    created = _invite(owner, "vic@example.com", "admin")
    client = client_factory()
    login(client, "vic@example.com")
    response = client.post(ACCEPT, json={"token": created["token"]})
    assert response.status_code == 200, response.text
    assert (response.json()["role"], response.json()["removed_at"]) == ("admin", None)


def test_a_refused_join_leaves_the_invite_unclaimed(owner, invitee):
    created = _invite(owner)
    add_member(owner, INVITEE, "viewer")  # joined another way after the invite went out
    response = invitee.post(ACCEPT, json={"token": created["token"]})
    assert (response.status_code, response.json()["detail"]) == (409, "Already a member")
    [row] = owner.get(INVITES, params={"status": "pending"}).json()["items"]
    assert (row["id"], row["accepted_at"]) == (created["id"], None)


def test_expired_invite_is_refused(owner, invitee, app):
    created = _invite(owner)
    with app.state.sessionmaker() as db:
        past = datetime.now(UTC) - timedelta(seconds=1)
        db.execute(update(Invite).where(Invite.id == created["id"]).values(expires_at=past))
        db.commit()
    [row] = owner.get(INVITES, params={"status": "expired"}).json()["items"]
    assert row["status"] == "expired"
    response = invitee.post(ACCEPT, json={"token": created["token"]})
    assert (response.status_code, response.json()["detail"]) == (410, "Invite expired")
    assert _invite(owner)["status"] == "pending"


def test_revoked_invite_is_refused(owner, invitee):
    created = _invite(owner)
    assert owner.delete(f"{INVITES}/{created['id']}").status_code == 204
    assert owner.delete(f"{INVITES}/{created['id']}").status_code == 204
    response = invitee.post(ACCEPT, json={"token": created["token"]})
    assert (response.status_code, response.json()["detail"]) == (410, "Invite revoked")
    [row] = owner.get(INVITES, params={"status": "revoked"}).json()["items"]
    assert row["revoked_at"] is not None
    assert sorted(_actions(owner, created["id"])) == [("invite.create", "ui"), ("invite.revoke", "ui")]


def test_unknown_token_and_wrong_email(owner, invitee, globex):
    assert invitee.post(ACCEPT, json={"token": "tji_nope"}).status_code == 404
    created = _invite(owner)
    owner.delete(f"{INVITES}/{created['id']}")
    # The wrong user learns nothing about the invite's state: 403, not 410.
    response = globex.post(ACCEPT, json={"token": created["token"]})
    assert (response.status_code, response.json()["detail"]) == (403, "This invite is for another email")


def test_an_api_token_cannot_accept(owner, client_factory):
    created = _invite(owner)
    token = owner.post("/api/v1/orgs/acme/tokens", json={"name": "t", "scopes": ["read"]}).json()["token"]
    assert bearer(client_factory, token).post(ACCEPT, json={"token": created["token"]}).status_code == 403


def test_revoke_rules(owner, invitee, globex, app):
    created = _invite(owner)
    assert globex.delete(f"/api/v1/orgs/globex/invites/{created['id']}").status_code == 404
    assert owner.delete(f"{INVITES}/01NOTANINVITE000000000000").status_code == 404
    assert invitee.post(ACCEPT, json={"token": created["token"]}).status_code == 200
    assert owner.delete(f"{INVITES}/{created['id']}").status_code == 409
    with app.state.sessionmaker() as db:
        assert db.scalar(select(Invite.revoked_at).where(Invite.id == created["id"])) is None


def test_invites_are_per_org(owner, globex):
    _invite(owner)
    assert globex.get("/api/v1/orgs/globex/invites").json()["items"] == []
    assert globex.get(INVITES).status_code == 404


@pytest.fixture
def spec(client_factory):
    response = client_factory().get("/api/v1/openapi.json")
    assert response.status_code == 200
    return {
        op["operationId"]: op
        for path in response.json()["paths"].values()
        for op in path.values()
        if isinstance(op, dict) and "operationId" in op
    }


@pytest.mark.parametrize("name", ["invites_create", "invites_list", "invites_revoke"])
def test_admin_operations_are_marked(spec, name):
    assert (spec[name]["x-scope"], spec[name]["x-toolset"], spec[name]["x-mcp"]) == ("admin", "admin", True)


def test_accept_is_not_an_mcp_tool(spec):
    assert spec["invites_accept"]["x-mcp"] is False
    assert spec["invites_accept"].get("x-scope") is None
