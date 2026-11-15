from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.schemas import AuditOut, Page
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_any_scope
from test_junkie_tcms.auth.scopes import ADMIN, AUDIT_READ
from test_junkie_tcms.db.models import AuditEvent

router = APIRouter(tags=["audit"])


@router.get("/orgs/{org}/audit", response_model=Page[AuditOut], **op("audit_list", AUDIT_READ, "admin"))
def audit_list(
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    since: datetime | None = Query(None, description="From this time, inclusive"),
    until: datetime | None = Query(None, description="Up to this time, exclusive"),
    via: Literal["ui", "api", "mcp"] | None = Query(None),
    action: str | None = Query(None, description="Exact action, e.g. invite.create"),
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
    rows, cursor = paginate(db, query, AuditEvent.id, params)
    return Page[AuditOut](items=rows, next_cursor=cursor)
