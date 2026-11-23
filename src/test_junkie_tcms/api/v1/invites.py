"""Invites: an admin invites an email to an org; the invitee accepts with the token, signed in, or
signs up on accept when the email has no account yet."""

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.orgs import _check_owner_rights, _member_out, join_org
from test_junkie_tcms.api.v1.schemas import (
    InviteAccept,
    InviteCreate,
    InviteCreated,
    InviteOut,
    InviteStatus,
    MemberOut,
    Page,
)
from test_junkie_tcms.auth import sessions
from test_junkie_tcms.auth.deps import (
    OrgContext,
    Principal,
    get_db,
    get_principal,
    get_settings,
    member_role,
    require_scope,
)
from test_junkie_tcms.auth.passwords import hash_password
from test_junkie_tcms.auth.scopes import ADMIN, ROLE_SCOPES
from test_junkie_tcms.auth.tokens import token_hash
from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import Actor, Invite, Membership, Org, User
from test_junkie_tcms.settings import Settings

router = APIRouter(tags=["invites"])
INVITES = "/orgs/{org}/invites"
EXPIRES_IN = timedelta(days=7)


def _status(row: Invite, now: datetime) -> str:
    if row.revoked_at is not None:
        return "revoked"
    if row.accepted_at is not None:
        return "accepted"
    if aware(row.expires_at) <= now:
        return "expired"
    return "pending"


def _invite_out(row: Invite, now: datetime | None = None) -> InviteOut:
    fields = {name: getattr(row, name) for name in InviteOut.model_fields if name != "status"}
    return InviteOut(**fields, status=_status(row, now or utcnow()))


@router.get(INVITES, response_model=Page[InviteOut], **op("invites_list", ADMIN, "admin"))
def invites_list(
    status: InviteStatus | None = Query(None, description="Default: open invites (pending and expired)"),
    ctx: OrgContext = Depends(require_scope(ADMIN)),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    now = utcnow()
    query = select(Invite).where(Invite.org_id == ctx.org.id)
    is_open = (Invite.revoked_at.is_(None), Invite.accepted_at.is_(None))
    if status is None:
        query = query.where(*is_open)
    elif status == "pending":
        query = query.where(*is_open, Invite.expires_at > now)
    elif status == "expired":
        query = query.where(*is_open, Invite.expires_at <= now)
    elif status == "accepted":
        query = query.where(Invite.revoked_at.is_(None), Invite.accepted_at.is_not(None))
    else:
        query = query.where(Invite.revoked_at.is_not(None))
    rows, cursor, total = paginate(db, query, Invite.id, params)
    return Page[InviteOut](items=[_invite_out(r, now) for r in rows], next_cursor=cursor, total=total)


# No Idempotency-Key here: its stored response would keep the plaintext token (as tokens_create).
@router.post(INVITES, status_code=201, response_model=InviteCreated, **op("invites_create", ADMIN, "admin"))
def invites_create(
    body: InviteCreate, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    _check_owner_rights(ctx, body.role)
    email = body.email.strip().lower()
    user_id = db.scalar(select(User.id).where(User.email == email))
    if user_id is not None and member_role(db, ctx.org.id, user_id) is not None:
        raise HTTPException(409, "Already a member")
    now = utcnow()
    open_invites = db.scalars(
        select(Invite).where(
            Invite.org_id == ctx.org.id,
            Invite.email == email,
            Invite.revoked_at.is_(None),
            Invite.accepted_at.is_(None),
        )
    )
    if any(_status(i, now) == "pending" for i in open_invites):
        raise HTTPException(409, "A pending invite for this email exists; revoke it to send again")
    token = f"tji_{secrets.token_urlsafe(32)}"
    row = Invite(
        org_id=ctx.org.id,
        email=email,
        role=body.role,
        token_hash=token_hash(token),
        invited_by_actor_id=ctx.actor.id,
        created_at=now,
        expires_at=now + EXPIRES_IN,
    )
    db.add(row)
    db.flush()
    audit.record(db, ctx, "invite.create", "invite", row.id, {"email": email, "role": body.role})
    db.commit()
    return InviteCreated(**_invite_out(row, now).model_dump(), token=token)


@router.delete(INVITES + "/{invite_id}", status_code=204, **op("invites_revoke", ADMIN, "admin"))
def invites_revoke(
    invite_id: str, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    row = db.scalar(select(Invite).where(Invite.org_id == ctx.org.id, Invite.id == invite_id))
    if row is None:
        raise HTTPException(404, "Invite not found")
    if row.accepted_at is not None:
        raise HTTPException(409, "Invite already accepted; remove the member instead")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        audit.record(db, ctx, "invite.revoke", "invite", row.id, {"email": row.email})
        db.commit()
    return Response(status_code=204)


def _user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def _check_open(row: Invite) -> None:
    status = _status(row, utcnow())
    if status == "revoked":
        raise HTTPException(410, "Invite revoked")
    if status == "accepted":
        raise HTTPException(410, "Invite already used")
    if status == "expired":
        raise HTTPException(410, "Invite expired")


def _claim(db: Session, row: Invite) -> None:
    # Claim the invite before joining, with a conditional update: a concurrent accept waits on the
    # row lock, then matches no row and gets 410 instead of a membership unique-key error.
    used = db.execute(
        update(Invite)
        .where(Invite.id == row.id, Invite.accepted_at.is_(None), Invite.revoked_at.is_(None))
        .values(accepted_at=utcnow())
    )
    if used.rowcount != 1:
        db.rollback()
        raise HTTPException(410, "Invite already used")


def _join(db: Session, row: Invite, principal: Principal, signed_up: bool) -> Membership:
    user = principal.user
    m = join_org(db, row.org_id, user, row.role)
    # accepted_user_id references the membership, so it is set once the join has made one.
    db.execute(update(Invite).where(Invite.id == row.id).values(accepted_user_id=user.id))
    actor = db.scalar(select(Actor).where(Actor.org_id == row.org_id, Actor.user_id == user.id))
    ctx = OrgContext(
        org=db.get(Org, row.org_id),
        actor=actor,
        role=row.role,
        scopes=ROLE_SCOPES[row.role],
        principal=principal,
    )
    detail = {"user_id": user.id, "role": row.role, "signed_up": signed_up}
    audit.record(db, ctx, "invite.accept", "invite", row.id, detail)
    return m


@router.post("/invites:accept", response_model=MemberOut, **op("invites_accept", None, "admin", mcp=False))
def invites_accept(
    body: InviteAccept,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Accept an invite. Signed in: send only `token`. No account yet: send `token`, `name` and
    `password`, with no sign-in; this creates the user, joins the org and starts a session (its cookies
    replace any session the caller had). An email that already has an account gets 409: sign in, then
    accept."""
    if body.password is None:
        return _accept_signed_in(body, get_principal(request, db, settings), db)
    # Hash before the claim, so the invite row isn't locked while argon2 runs.
    password_hash = hash_password(body.password)
    row = db.scalar(select(Invite).where(Invite.token_hash == token_hash(body.token)))
    if row is None:
        raise HTTPException(404, "Invite not found")
    _check_open(row)
    if _user_by_email(db, row.email) is not None:
        raise HTTPException(409, "An account exists for this email; sign in, then accept")
    _claim(db, row)
    user = User(email=row.email, name=body.name, password_hash=password_hash)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        # The email signed up another way since the check; the rollback unclaims the invite too.
        db.rollback()
        raise HTTPException(409, "An account exists for this email; sign in, then accept") from None
    session, cookie, csrf = sessions.start_session(
        db, settings, user, request.client.host if request.client else None, request.headers.get("user-agent")
    )
    m = _join(db, row, Principal(via="ui", user=user, session=session), signed_up=True)
    db.commit()
    sessions.set_cookies(response, settings, cookie, csrf)
    return _member_out(db, db.get(Membership, m.id))


def _accept_signed_in(body: InviteAccept, principal: Principal, db: Session) -> MemberOut:
    if principal.user is None:
        raise HTTPException(403, "Sign in to accept an invite; API tokens can't")
    row = db.scalar(select(Invite).where(Invite.token_hash == token_hash(body.token)))
    if row is None:
        raise HTTPException(404, "Invite not found")
    # The email check comes first, so a leaked token tells the wrong user nothing about the invite.
    if principal.user.email != row.email:
        raise HTTPException(403, "This invite is for another email")
    _check_open(row)
    _claim(db, row)
    m = _join(db, row, principal, signed_up=False)
    db.commit()
    return _member_out(db, db.get(Membership, m.id))
