"""Consumers: machines that run tests for an org. Status is derived, never stored."""

import hashlib
import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, count, page_params, paginate
from test_junkie_tcms.api.v1.cases import case_key
from test_junkie_tcms.api.v1.execution_schemas import JobOut
from test_junkie_tcms.api.v1.job_queue import (
    HELD,
    ONLINE_WITHIN,
    consumer_status,
    fail_consumer_jobs,
    stall_check,
)
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
    RosterItem,
)
from test_junkie_tcms.auth.deps import (
    ConsumerContext,
    OrgContext,
    get_consumer_context,
    get_db,
    require_scope,
)
from test_junkie_tcms.auth.scopes import ADMIN, CONSUMER, READ
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import (
    Actor,
    ApiToken,
    Consumer,
    ConsumerHeartbeat,
    ConsumerInventory,
    ConsumerProduct,
    Cycle,
    Job,
    Product,
    TestCase,
)

router = APIRouter(tags=["consumers"])
CONSUMERS = "/orgs/{org}/consumers"
ME = "/consumers/me"

HISTORY = timedelta(hours=24)


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


def consumer_project_counts(db: Session, consumer_ids: list[str]) -> dict[str, int]:
    """Projects in each consumer's last inventory, one grouped query for the whole page."""
    found = dict.fromkeys(consumer_ids, 0)
    rows = db.execute(
        select(ConsumerInventory.consumer_id, func.count())
        .where(ConsumerInventory.consumer_id.in_(consumer_ids))
        .group_by(ConsumerInventory.consumer_id)
    )
    for consumer_id, n in rows:
        found[consumer_id] = n
    return found


def consumer_out(consumer: Consumer, product_ids: list[str], project_count: int, now) -> ConsumerOut:
    return ConsumerOut(
        id=consumer.id,
        name=consumer.name,
        status=consumer_status(consumer, now),
        product_ids=product_ids,
        project_count=project_count,
        last_heartbeat_at=consumer.last_heartbeat_at,
        busy_job_id=consumer.busy_job_id,
        tj_version=consumer.tj_version,
        python=consumer.python,
        os=consumer.os,
        paused_at=consumer.paused_at,
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
    rows, cursor, total = paginate(db, query, Consumer.id, params)
    ids = [r.id for r in rows]
    products = consumer_product_ids(db, ids)
    projects = consumer_project_counts(db, ids)
    items = [consumer_out(r, products[r.id], projects[r.id], now) for r in rows]
    return Page[ConsumerOut](items=items, next_cursor=cursor, total=total)


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
    ).all()
    base = consumer_out(row, consumer_product_ids(db, [row.id])[row.id], len(inventory), now)
    recent = _jobs_query(ctx, row.id).where(Job.created_at >= now - HISTORY)
    rejected = recent.where(Job.status == "rejected")
    roster = _roster(db, ctx, inventory)
    return ConsumerDetail(
        **base.model_dump(),
        heartbeats=[HeartbeatOut.model_validate(b) for b in beats],
        inventory=[InventorySummary.model_validate(i) for i in inventory],
        jobs_today=count(db, recent),
        rejected_today=count(db, rejected),
        tests_found=len(roster),
        tests_linked=sum(1 for item in roster if item.case_key is not None),
    )


def _jobs_query(ctx: OrgContext, consumer_id: str):
    """The consumer's jobs whose cycle is in a product the caller sees."""
    query = select(Job).join(Cycle, Cycle.id == Job.cycle_id).where(Job.consumer_id == consumer_id)
    if ctx.product_ids is not None:
        query = query.where(Cycle.product_id.in_(ctx.product_ids))
    return query


def _roster(db: Session, ctx: OrgContext, inventory: list[ConsumerInventory]) -> list[RosterItem]:
    """Each ref of the inventory, by project, linked to the live case whose automation_ref it is when the
    caller sees that case's product."""
    pairs = [
        (i.project, t["id"])
        for i in inventory
        for t in i.roster
        if isinstance(t, dict) and isinstance(t.get("id"), str)
    ]
    refs = sorted({ref for _, ref in pairs})
    keys: dict[str, str] = {}
    for chunk in (refs[i : i + 500] for i in range(0, len(refs), 500)):
        query = (
            select(TestCase, Product)
            .join(Product, Product.id == TestCase.product_id)
            .where(
                TestCase.org_id == ctx.org.id,
                TestCase.archived_at.is_(None),
                TestCase.automation_ref.in_(chunk),
            )
            .order_by(TestCase.product_id, TestCase.number)
        )
        if ctx.product_ids is not None:
            query = query.where(TestCase.product_id.in_(ctx.product_ids))
        for case, product in db.execute(query):
            keys.setdefault(case.automation_ref, case_key(product, case))
    return [RosterItem(project=p, ref=r, case_key=keys.get(r)) for p, r in pairs]


@router.get(
    CONSUMERS + "/{consumer_id}/jobs",
    response_model=Page[JobOut],
    **op("consumers_jobs", READ, "consumers"),
)
def consumers_jobs(
    consumer_id: str = Path(),
    status: Literal["queued", "claimed", "running", "done", "failed", "cancelled", "rejected"] | None = None,
    ctx: OrgContext = Depends(require_scope(READ)),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    """The jobs sent to this machine, newest first, each with its `reason` when it was rejected or failed.
    Only jobs in products you can see."""
    row = _get(db, ctx, consumer_id)
    query = _jobs_query(ctx, row.id)
    if status is not None:
        query = query.where(Job.status == status)
    rows, cursor, total = paginate(db, query, Job.id, params, newest_first=True)
    items = [JobOut.model_validate(j, from_attributes=True) for j in rows]
    return Page[JobOut](items=items, next_cursor=cursor, total=total)


@router.get(
    CONSUMERS + "/{consumer_id}/roster",
    response_model=Page[RosterItem],
    **op("consumers_roster", READ, "consumers"),
)
def consumers_roster(
    consumer_id: str = Path(),
    project: str | None = Query(None, description="Only this project's refs"),
    ctx: OrgContext = Depends(require_scope(READ)),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    """The tests in the machine's last inventory, by project then as listed, each with the key of the case
    whose automation_ref it is (null when none you can see)."""
    row = _get(db, ctx, consumer_id)
    query = select(ConsumerInventory).where(ConsumerInventory.consumer_id == row.id)
    if project is not None:
        query = query.where(ConsumerInventory.project == project)
    roster = _roster(db, ctx, db.scalars(query.order_by(ConsumerInventory.project)).all())
    # The roster is one JSON list per project, so it pages by position; the cursor is the next offset.
    start = 0
    if params.cursor:
        if not params.cursor.isdigit():
            raise HTTPException(422, "cursor is not a next_cursor of this list")
        start = int(params.cursor)
    end = start + params.limit
    cursor = str(end) if end < len(roster) else None
    return Page[RosterItem](items=roster[start:end], next_cursor=cursor, total=len(roster))


def _set_paused(db: Session, ctx: OrgContext, consumer_id: str, paused: bool) -> ConsumerOut:
    row = _get(db, ctx, consumer_id)
    if row.revoked_at is not None:
        raise HTTPException(409, "The consumer is revoked; pair it again")
    if (row.paused_at is not None) != paused:
        row.paused_at = utcnow() if paused else None
        action = "consumer.pause" if paused else "consumer.resume"
        audit.record(db, ctx, action, "consumer", row.id, {"paused": {"from": not paused, "to": paused}})
        db.commit()
    ids = [row.id]
    return consumer_out(
        row, consumer_product_ids(db, ids)[row.id], consumer_project_counts(db, ids)[row.id], utcnow()
    )


@router.post(
    CONSUMERS + "/{consumer_id}/pause",
    response_model=ConsumerOut,
    **op("consumers_pause", ADMIN, "consumers"),
)
def consumers_pause(
    consumer_id: str = Path(), ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    """Stop sending it new jobs: claims return none and new cycles can't choose it. A job it holds runs to
    the end. Pausing a paused consumer changes nothing."""
    return _set_paused(db, ctx, consumer_id, True)


@router.post(
    CONSUMERS + "/{consumer_id}/resume",
    response_model=ConsumerOut,
    **op("consumers_resume", ADMIN, "consumers"),
)
def consumers_resume(
    consumer_id: str = Path(), ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    """It takes jobs again. Resuming a consumer that isn't paused changes nothing."""
    return _set_paused(db, ctx, consumer_id, False)


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
    return consumer_out(row, current, consumer_project_counts(db, [row.id])[row.id], utcnow())


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
        fail_consumer_jobs(db, row, now)
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
    """Every 30 s. Not audited; keeps 24 h of history. The server owns `busy_job_id`: the body's value is
    ignored. The reply lists jobs cancelled while this consumer held them."""
    now = utcnow()
    consumer = cc.consumer
    consumer.last_heartbeat_at = now
    consumer.tj_version = body.tj_version
    consumer.python = body.python
    consumer.os = body.os
    # The beat keeps the held job alive first, so a consumer back just after STALL_AFTER keeps its job.
    for job in db.scalars(select(Job).where(Job.consumer_id == consumer.id, Job.status.in_(HELD))):
        job.last_beat_at = now
    db.flush()
    stall_check(db, consumer.org_id, now)
    cancelled = db.scalars(
        select(Job).where(
            Job.consumer_id == consumer.id, Job.status == "cancelled", Job.cancel_sent_at.is_(None)
        )
    ).all()
    for job in cancelled:
        job.cancel_sent_at = now
    db.add(
        ConsumerHeartbeat(
            org_id=consumer.org_id, consumer_id=consumer.id, at=now, busy_job_id=consumer.busy_job_id
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
    return HeartbeatReply(inventory_wanted=wanted, cancel_job_ids=[j.id for j in cancelled])


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
