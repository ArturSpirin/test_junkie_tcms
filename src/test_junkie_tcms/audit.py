"""The audit log: one append-only `audit_event` and one `outbox` row per change, in the caller's
transaction."""

from typing import Any

from sqlalchemy.orm import Session

from test_junkie_tcms.auth.deps import OrgContext
from test_junkie_tcms.db.base import new_id
from test_junkie_tcms.db.models import AuditEvent, Outbox


def record(
    db: Session,
    ctx: OrgContext,
    action: str,
    entity_type: str,
    entity_id: str,
    changes: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=new_id(),
        org_id=ctx.org.id,
        actor_id=ctx.actor.id,
        **ctx.provenance(),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
    )
    db.add(event)
    db.flush()
    db.add(
        Outbox(
            org_id=ctx.org.id,
            audit_event_id=event.id,
            topic=action,
            payload={
                "event_id": event.id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "actor_id": event.actor_id,
            },
        )
    )
    return event
