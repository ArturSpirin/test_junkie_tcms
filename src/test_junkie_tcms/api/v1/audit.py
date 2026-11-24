from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.schemas import AuditOut, AuditRetentionOut, Page, UtcDateTime
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_any_scope
from test_junkie_tcms.auth.scopes import ADMIN, AUDIT_READ
from test_junkie_tcms.db.models import Actor, AuditEvent, Consumer

router = APIRouter(tags=["audit"])


@router.get("/orgs/{org}/audit", response_model=Page[AuditOut], **op("audit_list", AUDIT_READ, "admin"))
def audit_list(
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    since: UtcDateTime | None = Query(None, description="From this time, inclusive"),
    until: UtcDateTime | None = Query(None, description="Up to this time, exclusive"),
    via: Literal["ui", "api", "mcp"] | None = Query(None),
    action: str | None = Query(None, description="Exact action, e.g. invite.create"),
    actor_kind: Literal["user", "agent", "token", "consumer"] | None = Query(
        None, description="user: a member in the app; token: a member through a token; agent; consumer"
    ),
    q: str | None = Query(
        None, max_length=200, description="Text in the action, entity, actor name, request id or tool"
    ),
    ctx: OrgContext = Depends(require_any_scope(AUDIT_READ, ADMIN)),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    query = select(AuditEvent).where(AuditEvent.org_id == ctx.org.id)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    if actor_id:
        query = query.where(AuditEvent.actor_id == actor_id)
    if since:
        query = query.where(AuditEvent.created_at >= since)
    if until:
        query = query.where(AuditEvent.created_at < until)
    if via:
        query = query.where(AuditEvent.via == via)
    if action:
        query = query.where(AuditEvent.action == action)
    if actor_kind:
        query = query.where(_actor_kind(ctx.org.id, actor_kind))
    if q:
        text = q.lower()

        def has(col):
            return func.lower(col).contains(text, autoescape=True)

        named = select(Actor.id).where(Actor.org_id == ctx.org.id, has(Actor.name))
        query = query.where(
            or_(
                has(AuditEvent.action),
                has(AuditEvent.entity_type),
                has(AuditEvent.entity_id),
                has(AuditEvent.request_id),
                has(AuditEvent.tool),
                AuditEvent.actor_id.in_(named),
            )
        )
    rows, cursor, total = paginate(db, query, AuditEvent.id, params)
    return Page[AuditOut](items=rows, next_cursor=cursor, total=total)


@router.get(
    "/orgs/{org}/audit/retention",
    response_model=AuditRetentionOut,
    **op("audit_retention", AUDIT_READ, "admin"),
)
def audit_retention(
    request: Request,
    ctx: OrgContext = Depends(require_any_scope(AUDIT_READ, ADMIN)),
    db: Session = Depends(get_db),
):
    """The stated retention policy, and the oldest row actually kept: nothing purges audit_event yet."""
    oldest = db.scalar(select(func.min(AuditEvent.created_at)).where(AuditEvent.org_id == ctx.org.id))
    return AuditRetentionOut(days=request.app.state.audit_retention.days, oldest_kept=oldest)


def _actor_kind(org_id: str, kind: str):
    consumers = select(Consumer.actor_id).where(Consumer.org_id == org_id)
    if kind == "consumer":
        return AuditEvent.actor_id.in_(consumers)
    if kind == "agent":
        agents = select(Actor.id).where(
            Actor.org_id == org_id, Actor.kind == "agent", Actor.id.not_in(consumers)
        )
        return AuditEvent.actor_id.in_(agents)
    users = select(Actor.id).where(Actor.org_id == org_id, Actor.kind == "user")
    token = AuditEvent.token_id.is_not(None) if kind == "token" else AuditEvent.token_id.is_(None)
    return AuditEvent.actor_id.in_(users) & token
