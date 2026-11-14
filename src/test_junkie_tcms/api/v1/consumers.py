"""Consumers: machines that run tests for an org (PLAN-27 §4, PLAN-58). Status is derived, never stored."""

import hashlib
import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.schemas import (
    ConsumerDetail,
    ConsumerOut,
    ConsumerUpdate,
    HeartbeatIn,
    HeartbeatOut,
    HeartbeatReply,
    InventoryIn,
    InventoryReply,
    InventorySummary,
    Page,
)
from test_junkie_tcms.auth.deps import (
    ConsumerContext,
    OrgContext,
    get_consumer_context,
    get_db,
    require_scope,
)
from test_junkie_tcms.auth.scopes import ADMIN, CONSUMER, READ
from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import (
    Actor,
    ApiToken,
    Consumer,
    ConsumerHeartbeat,
    ConsumerInventory,
    ConsumerProduct,
    Product,
)

router = APIRouter(tags=["consumers"])
CONSUMERS = "/orgs/{org}/consumers"
ME = "/consumers/me"

ONLINE_WITHIN = timedelta(seconds=90)
HISTORY = timedelta(hours=24)


def consumer_status(consumer: Consumer, now) -> str:
    if consumer.revoked_at is not None:
        return "revoked"
    seen = aware(consumer.last_heartbeat_at)
    if seen is None or now - seen >= ONLINE_WITHIN:
        return "offline"
    return "busy" if consumer.busy_job_id else "online"


def consumer_product_ids(db: Session, consumer_ids: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {i: [] for i in consumer_ids}
    rows = db.execute(
        select(ConsumerProduct.consumer_id, ConsumerProduct.product_id)
        .where(ConsumerProduct.consumer_id.in_(consumer_ids))
        .order_by(ConsumerProduct.product_id)
    )
    for consumer_id, product_id in rows:
        found[consumer_id].append(product_id)
    return found


def consumer_out(consumer: Consumer, product_ids: list[str], now) -> ConsumerOut:
    return ConsumerOut(
        id=consumer.id,
        name=consumer.name,
        status=consumer_status(consumer, now),
        product_ids=product_ids,
        last_heartbeat_at=consumer.last_heartbeat_at,
        busy_job_id=consumer.busy_job_id,
        tj_version=consumer.tj_version,
        python=consumer.python,
        os=consumer.os,
        revoked_at=consumer.revoked_at,
        created_at=consumer.created_at,
    )


def check_name_free(db: Session, org_id: str, name: str, but: str | None = None) -> None:
    query = select(Consumer.id).where(
        Consumer.org_id == org_id, Consumer.name == name, Consumer.revoked_at.is_(None)
    )
    if but is not None:
        query = query.where(Consumer.id != but)
    if db.scalar(query) is not None:
        raise HTTPException(409, f"A consumer is already named {name!r}")


def check_products(db: Session, ctx: OrgContext, wanted: list[str]) -> list[str]:
    ids = sorted(set(wanted))
    found = set(db.scalars(select(Product.id).where(Product.org_id == ctx.org.id, Product.id.in_(ids))))
    unknown = [i for i in ids if i not in found or not ctx.sees_product(i)]
    if unknown:
        raise HTTPException(422, f"Unknown products: {', '.join(unknown)}")
    return ids


def _visible(ctx: OrgContext):
    """A product-limited caller sees the consumers that serve one of its products."""
    if ctx.product_ids is None:
        return None
    return Consumer.id.in_(
        select(ConsumerProduct.consumer_id).where(ConsumerProduct.product_id.in_(ctx.product_ids))
    )


def _get(db: Session, ctx: OrgContext, consumer_id: str) -> Consumer:
    query = select(Consumer).where(Consumer.org_id == ctx.org.id, Consumer.id == consumer_id)
    visible = _visible(ctx)
    if visible is not None:
        query = query.where(visible)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, "Consumer not found")
    return row


@router.get(CONSUMERS, response_model=Page[ConsumerOut], **op("consumers_list", READ, "consumers"))
def consumers_list(
    status: Literal["online", "offline", "busy", "revoked"] | None = Query(
        None, description="Revoked consumers show only with status=revoked"
    ),
    product: str | None = Query(None, description="Only consumers that serve this product id"),
    ctx: OrgContext = Depends(require_scope(READ)),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    now = utcnow()
    cutoff = now - ONLINE_WITHIN
    query = select(Consumer).where(Consumer.org_id == ctx.org.id)
    if status == "revoked":
        query = query.where(Consumer.revoked_at.is_not(None))
    else:
        query = query.where(Consumer.revoked_at.is_(None))
    if status == "offline":
        query = query.where(or_(Consumer.last_heartbeat_at.is_(None), Consumer.last_heartbeat_at < cutoff))
    elif status in ("online", "busy"):
        query = query.where(Consumer.last_heartbeat_at >= cutoff)
        busy = Consumer.busy_job_id.is_not(None)
        query = query.where(busy if status == "busy" else ~busy)
    if product is not None:
        query = query.where(
            Consumer.id.in_(select(ConsumerProduct.consumer_id).where(ConsumerProduct.product_id == product))
        )
    visible = _visible(ctx)
    if visible is not None:
        query = query.where(visible)
    rows, cursor = paginate(db, query, Consumer.id, params)
    products = consumer_product_ids(db, [r.id for r in rows])
    items = [consumer_out(r, products[r.id], now) for r in rows]
    return Page[ConsumerOut](items=items, next_cursor=cursor)


@router.get(
    CONSUMERS + "/{consumer_id}", response_model=ConsumerDetail, **op("consumers_get", READ, "consumers")
)
def consumers_get(
    consumer_id: str = Path(), ctx: OrgContext = Depends(require_scope(READ)), db: Session = Depends(get_db)
):
    now = utcnow()
    row = _get(db, ctx, consumer_id)
    beats = db.scalars(
        select(ConsumerHeartbeat)
        .where(ConsumerHeartbeat.consumer_id == row.id, ConsumerHeartbeat.at >= now - HISTORY)
        .order_by(ConsumerHeartbeat.at.desc())
    )
    inventory = db.scalars(
        select(ConsumerInventory)
        .where(ConsumerInventory.consumer_id == row.id)
        .order_by(ConsumerInventory.project)
    )
    base = consumer_out(row, consumer_product_ids(db, [row.id])[row.id], now)
    return ConsumerDetail(
        **base.model_dump(),
        heartbeats=[HeartbeatOut.model_validate(b) for b in beats],
        inventory=[InventorySummary.model_validate(i) for i in inventory],
    )


@router.patch(
    CONSUMERS + "/{consumer_id}", response_model=ConsumerOut, **op("consumers_update", ADMIN, "consumers")
)
def consumers_update(
    body: ConsumerUpdate,
    consumer_id: str = Path(),
    ctx: OrgContext = Depends(require_scope(ADMIN)),
    db: Session = Depends(get_db),
):
    row = _get(db, ctx, consumer_id)
    if row.revoked_at is not None:
        raise HTTPException(409, "The consumer is revoked; pair it again")
    changes = {}
    if body.name is not None and body.name != row.name:
        check_name_free(db, ctx.org.id, body.name, but=row.id)
        changes["name"] = {"from": row.name, "to": body.name}
        row.name = body.name
        db.get(Actor, row.actor_id).name = body.name
    current = consumer_product_ids(db, [row.id])[row.id]
    if body.product_ids is not None:
        ids = check_products(db, ctx, body.product_ids)
        if ids != current:
            db.execute(delete(ConsumerProduct).where(ConsumerProduct.consumer_id == row.id))
            db.add_all(ConsumerProduct(org_id=ctx.org.id, consumer_id=row.id, product_id=i) for i in ids)
            if row.token_id is not None:
                db.get(ApiToken, row.token_id).product_ids = ids
            changes["product_ids"] = {"from": current, "to": ids}
            current = ids
    if changes:
        audit.record(db, ctx, "consumer.update", "consumer", row.id, changes)
        db.commit()
    return consumer_out(row, current, utcnow())


@router.delete(CONSUMERS + "/{consumer_id}", status_code=204, **op("consumers_revoke", ADMIN, "consumers"))
def consumers_revoke(
    consumer_id: str = Path(), ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    row = _get(db, ctx, consumer_id)
    if row.revoked_at is None:
        now = utcnow()
        row.revoked_at = now
        if row.token_id is not None:
            token = db.get(ApiToken, row.token_id)
            token.revoked_at = token.revoked_at or now
        actor = db.get(Actor, row.actor_id)
        actor.disabled_at = actor.disabled_at or now
        audit.record(db, ctx, "consumer.revoke", "consumer", row.id, {"name": row.name})
        db.commit()
    return Response(status_code=204)


# The consumer side: only a paired consumer's own token reaches these.


@router.post(
    ME + "/heartbeat",
    response_model=HeartbeatReply,
    **op("consumers_heartbeat", CONSUMER, "consumers", mcp=False),
)
def consumers_heartbeat(
    body: HeartbeatIn, cc: ConsumerContext = Depends(get_consumer_context), db: Session = Depends(get_db)
):
    """Every 30 s. Not audited; keeps 24 h of history."""
    now = utcnow()
    consumer = cc.consumer
    consumer.last_heartbeat_at = now
    consumer.busy_job_id = body.busy_job_id
    consumer.tj_version = body.tj_version
    consumer.python = body.python
    consumer.os = body.os
    db.add(
        ConsumerHeartbeat(
            org_id=consumer.org_id, consumer_id=consumer.id, at=now, busy_job_id=body.busy_job_id
        )
    )
    db.execute(
        delete(ConsumerHeartbeat).where(
            ConsumerHeartbeat.consumer_id == consumer.id, ConsumerHeartbeat.at < now - HISTORY
        )
    )
    stored = dict(
        db.execute(
            select(ConsumerInventory.project, ConsumerInventory.hash).where(
                ConsumerInventory.consumer_id == consumer.id
            )
        ).all()
    )
    wanted = sorted(p for p, h in body.inventory_hashes.items() if stored.get(p) != h)
    db.commit()
    return HeartbeatReply(inventory_wanted=wanted, cancel_job_ids=[])


def roster_hash(roster: list) -> str:
    """SHA-256 of the canonical JSON: sorted keys, no spaces."""
    canonical = json.dumps(roster, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


@router.put(
    ME + "/inventory/{project}",
    response_model=InventoryReply,
    **op("consumers_put_inventory", CONSUMER, "consumers", mcp=False),
)
def consumers_put_inventory(
    body: InventoryIn,
    project: str = Path(min_length=1, max_length=200),
    cc: ConsumerContext = Depends(get_consumer_context),
    db: Session = Depends(get_db),
):
    """Stored by hash: the same hash as stored writes nothing and audits nothing."""
    if roster_hash(body.roster) != body.hash:
        raise HTTPException(422, "hash is not the SHA-256 of the canonical roster")
    consumer = cc.consumer
    row = db.scalar(
        select(ConsumerInventory).where(
            ConsumerInventory.consumer_id == consumer.id, ConsumerInventory.project == project
        )
    )
    if row is not None and row.hash == body.hash:
        return InventoryReply(changed=False, test_count=row.test_count)
    if row is None:
        row = ConsumerInventory(org_id=consumer.org_id, consumer_id=consumer.id, project=project)
        db.add(row)
    row.hash = body.hash
    row.roster = body.roster
    row.test_count = len(body.roster)
    db.flush()
    changes = {"project": project, "hash": body.hash, "test_count": row.test_count}
    audit.record(db, cc.ctx, "consumer.inventory", "consumer", consumer.id, changes)
    db.commit()
    return InventoryReply(changed=True, test_count=row.test_count)
