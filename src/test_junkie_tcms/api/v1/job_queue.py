"""The job queue: split a cycle's automated cases between consumers, and requeue or fail
a job whose consumer stopped beating. Cycles, jobs and consumers all use it, so it imports none of them."""

from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.auth.deps import OrgContext, Principal
from test_junkie_tcms.auth.scopes import CONSUMER
from test_junkie_tcms.db.base import aware
from test_junkie_tcms.db.models import (
    Actor,
    CaseVersion,
    Consumer,
    ConsumerInventory,
    ConsumerProduct,
    Cycle,
    CycleCase,
    Job,
    Org,
)
from test_junkie_tcms.errors import ProblemError

ONLINE_WITHIN = timedelta(seconds=90)
# A claimed job whose consumer sent no heartbeat for this long is requeued once, then failed.
STALL_AFTER = timedelta(seconds=120)
MAX_ATTEMPTS = 2
HELD = ("claimed", "running")
LOST = "consumer lost"


def consumer_status(consumer: Consumer, now) -> str:
    if consumer.revoked_at is not None:
        return "revoked"
    seen = aware(consumer.last_heartbeat_at)
    if seen is None or now - seen >= ONLINE_WITHIN:
        return "offline"
    return "busy" if consumer.busy_job_id else "online"


def online(consumer: Consumer, now) -> bool:
    return consumer_status(consumer, now) in ("online", "busy")


def serves(db: Session, consumer_id: str, product_id: str) -> bool:
    found = db.scalar(
        select(ConsumerProduct.id).where(
            ConsumerProduct.consumer_id == consumer_id, ConsumerProduct.product_id == product_id
        )
    )
    return found is not None


def rosters(db: Session, consumer_ids: list[str]) -> dict[str, dict[str, set[str]]]:
    """Consumer id to project to the test ids its last inventory listed."""
    out: dict[str, dict[str, set[str]]] = {i: {} for i in consumer_ids}
    rows = db.scalars(
        select(ConsumerInventory)
        .where(ConsumerInventory.consumer_id.in_(consumer_ids))
        .order_by(ConsumerInventory.project)
    )
    for row in rows:
        out[row.consumer_id][row.project] = {t["id"] for t in row.roster if isinstance(t, dict) and "id" in t}
    return out


def check_consumers(db: Session, org_id: str, product_id: str, ids: list[str], now) -> list[Consumer]:
    """The chosen consumers in the given order.

    404 not in the org, 422 not serving the product, 409 offline."""
    found = []
    for consumer_id in dict.fromkeys(ids):
        row = db.scalar(select(Consumer).where(Consumer.org_id == org_id, Consumer.id == consumer_id))
        if row is None:
            raise HTTPException(404, f"Consumer {consumer_id} not found")
        if not serves(db, row.id, product_id):
            raise HTTPException(422, f"Consumer {row.name!r} does not serve this product")
        if not online(row, now):
            raise ProblemError(409, f"Consumer {row.name!r} is offline", code="consumer_offline")
        found.append(row)
    return found


@dataclass
class Split:
    """Which items go to which (consumer, project), and what is left to people."""

    shares: dict[tuple[str, str], list] = field(default_factory=dict)
    refs: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    person: list = field(default_factory=list)
    unmatched: int = 0


def split_by_runner(db: Session, consumers: list[Consumer], items: list[tuple[object, CaseVersion]]) -> Split:
    """An item goes to a consumer when its pinned version is automated and its automation_ref is in that
    consumer's inventory; ties go to the consumer with the fewest cases so far, then the given order. One
    share per (consumer, project). An automated case no consumer lists counts as unmatched and goes to
    people."""
    out = Split()
    inventory = rosters(db, [c.id for c in consumers])
    load = {c.id: 0 for c in consumers}
    order = {c.id: i for i, c in enumerate(consumers)}
    for item, version in items:
        ref = version.automation_ref
        if version.automation != "automated" or not ref:
            out.person.append(item)
            continue
        candidates = []
        for c in consumers:
            project = next((p for p, refs in inventory[c.id].items() if ref in refs), None)
            if project is not None:
                candidates.append((load[c.id], order[c.id], c.id, project))
        if not candidates:
            out.person.append(item)
            out.unmatched += 1
            continue
        _, _, consumer_id, project = min(candidates)
        load[consumer_id] += 1
        key = (consumer_id, project)
        out.shares.setdefault(key, []).append(item)
        refs = out.refs.setdefault(key, [])
        if ref not in refs:
            refs.append(ref)
    return out


def make_jobs(db: Session, cycle: Cycle, plan: Split) -> list[Job]:
    """Queue one job per share and hand its cycle cases to the consumer."""
    jobs = []
    for (consumer_id, project), rows in plan.shares.items():
        job = Job(
            org_id=cycle.org_id,
            cycle_id=cycle.id,
            consumer_id=consumer_id,
            project=project,
            refs=plan.refs[(consumer_id, project)],
            status="queued",
        )
        db.add(job)
        db.flush()
        for cc in rows:
            cc.runner, cc.consumer_id, cc.job_id, cc.assignee_actor_id = "consumer", consumer_id, job.id, None
        jobs.append(job)
    return jobs


def system_ctx(db: Session, org_id: str, consumer: Consumer) -> OrgContext:
    """Acts as the consumer for what the server does on its behalf: requeue, fail, cancel results.
    A real `OrgContext`, so audit and provenance read it like any request's."""
    actor = db.get(Actor, consumer.actor_id)
    return OrgContext(
        org=db.get(Org, org_id),
        actor=actor,
        role=actor.role,
        scopes=frozenset({CONSUMER}),
        principal=Principal(via="api", actor=actor),
    )


def release(db: Session, job: Job) -> None:
    """The job's consumer is no longer busy with it."""
    consumer = db.get(Consumer, job.consumer_id)
    if consumer is not None and consumer.busy_job_id == job.id:
        consumer.busy_job_id = None


def cancel_open_cases(db: Session, ctx, job: Job, comment: str) -> int:
    """Each untested case of the job gets a `cancel` result from the consumer."""
    # Imported here: results imports cycles, which imports this module.
    from test_junkie_tcms.api.v1.catalog import to_doc
    from test_junkie_tcms.api.v1.results import record
    from test_junkie_tcms.api.v1.schemas import MarkdownIn

    rows = db.scalars(
        select(CycleCase)
        .where(CycleCase.job_id == job.id, CycleCase.status == "untested")
        .order_by(CycleCase.position)
    ).all()
    doc = to_doc("comment", MarkdownIn(markdown=comment))
    for cc in rows:
        record(db, ctx, cc, "consumer", "cancel", doc, None, [], [], [])
    return len(rows)


def pick_other(db: Session, job: Job, product_id: str, now) -> Consumer | None:
    """Another online consumer that serves the product and lists the job's project, least busy first."""
    rows = db.scalars(
        select(Consumer)
        .join(ConsumerProduct, ConsumerProduct.consumer_id == Consumer.id)
        .join(ConsumerInventory, ConsumerInventory.consumer_id == Consumer.id)
        .where(
            Consumer.org_id == job.org_id,
            Consumer.id != job.consumer_id,
            Consumer.revoked_at.is_(None),
            ConsumerProduct.product_id == product_id,
            ConsumerInventory.project == job.project,
        )
        .order_by(Consumer.id)
    ).all()
    live = [c for c in rows if online(c, now)]
    live.sort(key=lambda c: c.busy_job_id is not None)
    return live[0] if live else None


def requeue_or_fail(db: Session, job: Job, now, reason: str = LOST) -> None:
    """Requeue the job on another online consumer once; after that, or with none, fail it and cancel its
    open cases with `reason`."""
    lost = db.get(Consumer, job.consumer_id)
    ctx = system_ctx(db, job.org_id, lost)
    release(db, job)
    cycle = db.get(Cycle, job.cycle_id)
    target = pick_other(db, job, cycle.product_id, now) if job.attempts < MAX_ATTEMPTS else None
    if target is not None:
        changes = {"consumer_id": [job.consumer_id, target.id], "attempts": [job.attempts, job.attempts + 1]}
        job.consumer_id, job.status, job.attempts = target.id, "queued", job.attempts + 1
        job.claimed_at = job.last_beat_at = job.cancel_sent_at = None
        for cc in db.scalars(select(CycleCase).where(CycleCase.job_id == job.id)):
            cc.consumer_id = target.id
        audit.record(db, ctx, "job.requeue", "job", job.id, {**changes, "reason": reason})
        return
    job.status, job.finished_at = "failed", now
    cancelled = cancel_open_cases(db, ctx, job, reason)
    audit.record(db, ctx, "job.fail", "job", job.id, {"reason": reason, "cancelled": cancelled})


def stalled_ids(db: Session, org_id: str, cutoff) -> list[str]:
    return db.scalars(
        select(Job.id).where(Job.org_id == org_id, Job.status.in_(HELD), Job.last_beat_at < cutoff)
    ).all()


def take_stalled(db: Session, job_id: str, cutoff, now) -> Job | None:
    """Claims a stalled job for this check with a conditional update, the way jobs_next claims, so two
    overlapping checks can't both requeue or fail it: the loser's WHERE no longer matches."""
    taken = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(HELD), Job.last_beat_at < cutoff)
        .values(last_beat_at=now, updated_at=now)
    ).rowcount
    if taken != 1:
        return None
    job = db.get(Job, job_id)
    db.refresh(job)
    return job


def stall_check(db: Session, org_id: str, now) -> int:
    """Requeue or fail the org's held jobs with no heartbeat for STALL_AFTER. Runs inline from the heartbeat,
    jobs_next and jobs_list: there is no worker. Returns how many it moved; the caller commits."""
    cutoff = now - STALL_AFTER
    moved = 0
    for job_id in stalled_ids(db, org_id, cutoff):
        job = take_stalled(db, job_id, cutoff, now)
        if job is not None:
            requeue_or_fail(db, job, now)
            moved += 1
    return moved


def fail_consumer_jobs(db: Session, consumer: Consumer, now) -> None:
    """A revoked consumer's queued and held jobs go at once, by the stall rule."""
    jobs = db.scalars(
        select(Job).where(Job.consumer_id == consumer.id, Job.status.in_(("queued",) + HELD))
    ).all()
    for job in jobs:
        requeue_or_fail(db, job, now, "consumer revoked")
