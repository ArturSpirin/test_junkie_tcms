"""Request dependencies: the database session, who is calling, and what they may do in an org."""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms.auth import sessions, tokens
from test_junkie_tcms.auth.scopes import CONSUMER, ROLE_SCOPES, lower_role
from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import Actor, ApiToken, Consumer, Membership, Org, User, UserSession
from test_junkie_tcms.settings import Settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# ASGI scope key the MCP dispatcher sets on its in-process requests; no client header can set it.
MCP_VIA_KEY = "tcms.via_mcp"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.sessionmaker()
    try:
        yield db
    finally:
        db.close()


@dataclass
class Principal:
    via: str  # "ui" for a cookie session, "api" for a bearer token, "mcp" for a token over /mcp
    user: User | None = None
    session: UserSession | None = None
    token: ApiToken | None = None
    actor: Actor | None = None  # the token's actor; cookie principals get one per org


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def get_principal(
    request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> Principal:
    auth = request.headers.get("Authorization")
    if auth:
        scheme, _, value = auth.partition(" ")
        if scheme.lower() != "bearer" or not value:
            raise _unauthorized()
        found = tokens.authenticate_token(db, value.strip())
        if found is None:
            raise _unauthorized("Invalid, revoked or expired token")
        token, actor = found
        if CONSUMER in token.scopes:
            raise HTTPException(403, "A consumer token reaches only the consumer routes")
        via = "mcp" if request.scope.get(MCP_VIA_KEY) else "api"
        return Principal(via=via, token=token, actor=actor)

    cookie = request.cookies.get(sessions.SESSION_COOKIE)
    if not cookie:
        raise _unauthorized()
    row = sessions.find_session(db, settings, cookie)
    if row is None:
        raise _unauthorized("Session expired or signed out")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    if request.method not in SAFE_METHODS and not sessions.csrf_ok(
        settings,
        row,
        request.cookies.get(sessions.CSRF_COOKIE),
        request.headers.get(sessions.CSRF_HEADER),
    ):
        raise HTTPException(403, "CSRF token missing or wrong")
    return Principal(via="ui", user=user, session=row)


def member_role(db: Session, org_id: str, user_id: str) -> str | None:
    return db.scalar(
        select(Membership.role).where(
            Membership.org_id == org_id, Membership.user_id == user_id, Membership.removed_at.is_(None)
        )
    )


def effective_role(db: Session, actor: Actor) -> str | None:
    """A user's membership role; an agent's own role clamped to its owner's current role."""
    if actor.disabled_at is not None:
        return None
    if actor.kind == "user":
        return member_role(db, actor.org_id, actor.user_id)
    return lower_role(actor.role, member_role(db, actor.org_id, actor.owner_user_id))


@dataclass
class OrgContext:
    org: Org
    actor: Actor
    role: str
    scopes: frozenset[str]
    principal: Principal
    # A token limited to some products; None means every product in the org.
    product_ids: frozenset[str] | None = None

    def has(self, scope: str) -> bool:
        return scope in self.scopes

    def sees_product(self, product_id: str) -> bool:
        return self.product_ids is None or product_id in self.product_ids

    def provenance(self) -> dict[str, str | None]:
        """How this request acts: stored on every audit_event and case_version it writes."""
        token = self.principal.token
        return {
            "via": self.principal.via,
            "token_id": token.id if token is not None else None,
            "on_behalf_of_user_id": self.actor.owner_user_id,
        }


def _not_found() -> HTTPException:
    return HTTPException(404, "Org not found")


def touch_active(db: Session, actor: Actor) -> None:
    """Members' "last active": committed here, since a read-only request never commits."""
    now = utcnow()
    if actor.last_active_at is None or now - aware(actor.last_active_at) >= tokens.LAST_USED_EVERY:
        actor.last_active_at = now
        db.commit()


def get_org_context(
    org: str = Path(description="Org slug"),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> OrgContext:
    row = db.scalar(select(Org).where(Org.slug == org))
    if row is None:
        raise _not_found()
    if principal.token is not None:
        if principal.token.org_id != row.id:
            raise _not_found()
        actor = principal.actor
    else:
        actor = db.scalar(
            select(Actor).where(
                Actor.org_id == row.id, Actor.kind == "user", Actor.user_id == principal.user.id
            )
        )
        if actor is None:
            raise _not_found()
    role = effective_role(db, actor)
    if role is None:
        raise _not_found()
    touch_active(db, actor)
    scopes = ROLE_SCOPES[role]
    product_ids = None
    if principal.token is not None:
        scopes = scopes & frozenset(principal.token.scopes)
        if principal.token.product_ids is not None:
            product_ids = frozenset(principal.token.product_ids)
    return OrgContext(
        org=row, actor=actor, role=role, scopes=scopes, principal=principal, product_ids=product_ids
    )


@dataclass
class ConsumerContext:
    ctx: OrgContext
    consumer: Consumer


def get_consumer_context(request: Request, db: Session = Depends(get_db)) -> ConsumerContext:
    """The consumer side: only a paired consumer's own token, while its actor still has a role."""
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value:
        if request.cookies.get(sessions.SESSION_COOKIE):
            raise HTTPException(403, "Needs a consumer token")
        raise _unauthorized()
    found = tokens.authenticate_token(db, value.strip())
    if found is None:
        raise _unauthorized("Invalid, revoked or expired token")
    token, actor = found
    if token.scopes != [CONSUMER]:
        raise HTTPException(403, "Needs a consumer token")
    consumer = db.scalar(
        select(Consumer).where(Consumer.org_id == token.org_id, Consumer.actor_id == actor.id)
    )
    if consumer is None or consumer.revoked_at is not None or consumer.token_id != token.id:
        raise _unauthorized("Consumer revoked")
    role = effective_role(db, actor)
    if role is None:
        raise _unauthorized("The consumer's approver is no longer a member")
    touch_active(db, actor)
    product_ids = frozenset(token.product_ids) if token.product_ids is not None else None
    ctx = OrgContext(
        org=db.get(Org, token.org_id),
        actor=actor,
        role=role,
        scopes=frozenset({CONSUMER}),
        principal=Principal(via="api", token=token, actor=actor),
        product_ids=product_ids,
    )
    return ConsumerContext(ctx=ctx, consumer=consumer)


def require_scope(scope: str):
    def check(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        if not ctx.has(scope):
            raise HTTPException(403, f"Needs scope {scope}")
        return ctx

    return check


def require_any_scope(*scopes: str):
    def check(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        if not any(ctx.has(scope) for scope in scopes):
            raise HTTPException(403, f"Needs scope {' or '.join(scopes)}")
        return ctx

    return check
