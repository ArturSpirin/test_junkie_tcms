"""Orgs, their members and their agents."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.schemas import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    MemberAdd,
    MemberOut,
    MemberUpdate,
    OrgOut,
    OrgUpdate,
    Page,
)
from test_junkie_tcms.auth.deps import (
    OrgContext,
    Principal,
    effective_role,
    get_db,
    get_principal,
    member_role,
    require_scope,
)
from test_junkie_tcms.auth.passwords import hash_password
from test_junkie_tcms.auth.scopes import ADMIN, READ, ROLE_RANK
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import Actor, Membership, Org, User

router = APIRouter(tags=["orgs"])
ORG = "/orgs/{org}"


@router.get("/orgs", response_model=Page[OrgOut], **op("orgs_list", READ, "orgs"))
def orgs_list(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if principal.token is not None:
        actors = [principal.actor]
    else:
        actors = db.scalars(select(Actor).where(Actor.kind == "user", Actor.user_id == principal.user.id))
    orgs = [db.get(Org, a.org_id) for a in actors if effective_role(db, a)]
    return Page[OrgOut](items=sorted(orgs, key=lambda o: o.slug))


@router.get(ORG, response_model=OrgOut, **op("orgs_get", READ, "orgs"))
def orgs_get(ctx: OrgContext = Depends(require_scope(READ))):
    return ctx.org


@router.patch(ORG, response_model=OrgOut, **op("orgs_update", ADMIN, "admin"))
def orgs_update(
    body: OrgUpdate, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    old = ctx.org.name
    ctx.org.name = body.name
    audit.record(db, ctx, "org.update", "org", ctx.org.id, {"name": [old, body.name]})
    db.commit()
    return ctx.org


# Members


def _member_out(db: Session, m: Membership) -> MemberOut:
    user = db.get(User, m.user_id)
    actor = db.scalar(select(Actor).where(Actor.org_id == m.org_id, Actor.user_id == m.user_id))
    return MemberOut(
        user_id=user.id,
        actor_id=actor.id,
        email=user.email,
        name=user.name,
        role=m.role,
        removed_at=m.removed_at,
    )


def _get_member(db: Session, ctx: OrgContext, user_id: str) -> Membership:
    m = db.scalar(select(Membership).where(Membership.org_id == ctx.org.id, Membership.user_id == user_id))
    if m is None or m.removed_at is not None:
        raise HTTPException(404, "Member not found")
    return m


def _check_owner_rights(ctx: OrgContext, *roles: str) -> None:
    if "owner" in roles and ctx.role != "owner":
        raise HTTPException(403, "Only an owner can grant, change or remove the owner role")


def _active_owners(db: Session, org_id: str) -> int:
    return db.scalar(
        select(func.count()).where(
            Membership.org_id == org_id, Membership.role == "owner", Membership.removed_at.is_(None)
        )
    )


@router.get(ORG + "/members", response_model=Page[MemberOut], **op("members_list", READ, "admin"))
def members_list(
    ctx: OrgContext = Depends(require_scope(READ)),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    query = select(Membership).where(Membership.org_id == ctx.org.id, Membership.removed_at.is_(None))
    rows, cursor = paginate(db, query, Membership.id, params)
    return Page[MemberOut](items=[_member_out(db, m) for m in rows], next_cursor=cursor)


@router.post(ORG + "/members", status_code=201, response_model=MemberOut, **op("members_add", ADMIN, "admin"))
def members_add(
    body: MemberAdd, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    _check_owner_rights(ctx, body.role)
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email, name=body.name, password_hash=hash_password(body.password) if body.password else None
        )
        db.add(user)
        db.flush()
    m = db.scalar(select(Membership).where(Membership.org_id == ctx.org.id, Membership.user_id == user.id))
    if m is not None and m.removed_at is None:
        raise HTTPException(409, "Already a member")
    if m is None:
        m = Membership(org_id=ctx.org.id, user_id=user.id, role=body.role)
        db.add(m)
        db.flush()
        db.add(Actor(org_id=ctx.org.id, kind="user", name=user.name, user_id=user.id))
    else:
        m.role, m.removed_at = body.role, None
        actor = db.scalar(select(Actor).where(Actor.org_id == ctx.org.id, Actor.user_id == user.id))
        actor.disabled_at = None
    db.flush()
    audit.record(db, ctx, "member.add", "user", user.id, {"email": email, "role": body.role})
    db.commit()
    return _member_out(db, m)


@router.patch(ORG + "/members/{user_id}", response_model=MemberOut, **op("members_update", ADMIN, "admin"))
def members_update(
    user_id: str,
    body: MemberUpdate,
    ctx: OrgContext = Depends(require_scope(ADMIN)),
    db: Session = Depends(get_db),
):
    m = _get_member(db, ctx, user_id)
    _check_owner_rights(ctx, m.role, body.role)
    if m.role == "owner" and body.role != "owner" and _active_owners(db, ctx.org.id) <= 1:
        raise HTTPException(409, "An org keeps at least one owner")
    old = m.role
    m.role = body.role
    audit.record(db, ctx, "member.update", "user", user_id, {"role": [old, body.role]})
    db.commit()
    return _member_out(db, m)


@router.delete(ORG + "/members/{user_id}", status_code=204, **op("members_remove", ADMIN, "admin"))
def members_remove(
    user_id: str, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    m = _get_member(db, ctx, user_id)
    _check_owner_rights(ctx, m.role)
    if m.role == "owner" and _active_owners(db, ctx.org.id) <= 1:
        raise HTTPException(409, "An org keeps at least one owner")
    now = utcnow()
    m.removed_at = now
    actor = db.scalar(select(Actor).where(Actor.org_id == ctx.org.id, Actor.user_id == user_id))
    actor.disabled_at = now
    audit.record(db, ctx, "member.remove", "user", user_id, {"role": m.role})
    db.commit()


# Agents


def _get_agent(db: Session, ctx: OrgContext, agent_id: str) -> Actor:
    agent = db.scalar(
        select(Actor).where(Actor.org_id == ctx.org.id, Actor.id == agent_id, Actor.kind == "agent")
    )
    if agent is None:
        raise HTTPException(404, "Agent not found")
    return agent


def _check_agent_role(db: Session, ctx: OrgContext, owner_user_id: str, role: str) -> None:
    owner_role = member_role(db, ctx.org.id, owner_user_id)
    if owner_role is None:
        raise HTTPException(422, "The agent's owner must be a member of this org")
    if ROLE_RANK[role] > ROLE_RANK[owner_role]:
        raise HTTPException(422, f"An agent's role can't be above its owner's role ({owner_role})")


@router.get(ORG + "/agents", response_model=Page[AgentOut], **op("agents_list", ADMIN, "admin"))
def agents_list(
    ctx: OrgContext = Depends(require_scope(ADMIN)),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    query = select(Actor).where(Actor.org_id == ctx.org.id, Actor.kind == "agent")
    rows, cursor = paginate(db, query, Actor.id, params)
    return Page[AgentOut](items=rows, next_cursor=cursor)


@router.post(ORG + "/agents", status_code=201, response_model=AgentOut, **op("agents_create", ADMIN, "admin"))
def agents_create(
    body: AgentCreate, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    owner = body.owner_user_id or ctx.actor.user_id or ctx.actor.owner_user_id
    _check_agent_role(db, ctx, owner, body.role)
    agent = Actor(org_id=ctx.org.id, kind="agent", name=body.name, owner_user_id=owner, role=body.role)
    db.add(agent)
    db.flush()
    audit.record(db, ctx, "agent.create", "actor", agent.id, {"name": body.name, "role": body.role})
    db.commit()
    return agent


@router.patch(ORG + "/agents/{agent_id}", response_model=AgentOut, **op("agents_update", ADMIN, "admin"))
def agents_update(
    agent_id: str,
    body: AgentUpdate,
    ctx: OrgContext = Depends(require_scope(ADMIN)),
    db: Session = Depends(get_db),
):
    agent = _get_agent(db, ctx, agent_id)
    changes = {}
    if body.role is not None and body.role != agent.role:
        _check_agent_role(db, ctx, agent.owner_user_id, body.role)
        changes["role"] = [agent.role, body.role]
        agent.role = body.role
    if body.name is not None and body.name != agent.name:
        changes["name"] = [agent.name, body.name]
        agent.name = body.name
    if changes:
        audit.record(db, ctx, "agent.update", "actor", agent.id, changes)
        db.commit()
    return agent


@router.post(
    ORG + "/agents/{agent_id}/disable", response_model=AgentOut, **op("agents_disable", ADMIN, "admin")
)
def agents_disable(
    agent_id: str, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    agent = _get_agent(db, ctx, agent_id)
    if agent.disabled_at is None:
        agent.disabled_at = utcnow()
        audit.record(db, ctx, "agent.disable", "actor", agent.id)
        db.commit()
    return agent
