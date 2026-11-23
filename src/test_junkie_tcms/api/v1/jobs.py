"""Jobs: a consumer claims the automated part of a cycle and reports its results; people
cancel or reassign it. A job with no heartbeat for 2 min is requeued once, then failed (see job_queue)."""

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.catalog import to_doc
from test_junkie_tcms.api.v1.cycles import CYCLE, get_cycle
from test_junkie_tcms.api.v1.execution_schemas import JobOut, JobReassign, JobReportIn, JobReportOut
from test_junkie_tcms.api.v1.job_queue import (
    HELD,
    cancel_open_cases,
    check_consumers,
    release,
    rosters,
    stall_check,
)
from test_junkie_tcms.api.v1.results import record
from test_junkie_tcms.api.v1.schemas import MarkdownIn, Page
from test_junkie_tcms.auth.deps import (
    ConsumerContext,
    OrgContext,
    get_consumer_context,
    get_db,
    require_scope,
)
from test_junkie_tcms.auth.scopes import CONSUMER, READ, WRITE_EXECUTION
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import CaseVersion, Consumer, Cycle, CycleCase, Job
from test_junkie_tcms.errors import ProblemError

router = APIRouter(tags=["execution"])
MY_JOBS = "/consumers/me/jobs"
JOB = "/orgs/{org}/jobs/{id}"
MAX_WAIT = 30
FINISHED = ("done", "failed", "cancelled", "rejected")

# Hooks the tests patch: the long-poll's pause and clock.
_sleep = time.sleep
_clock = time.monotonic


def job_out(job: Job) -> JobOut:
    return JobOut.model_validate(job, from_attributes=True)


def get_job(db: Session, ctx: OrgContext, id_: str) -> Job:
    job = db.scalar(select(Job).where(Job.org_id == ctx.org.id, Job.id == id_))
    cycle = job and db.get(Cycle, job.cycle_id)
    if job is None or not ctx.sees_product(cycle.product_id):
        raise HTTPException(404, "Job not found")
    return job


def claim(db: Session, consumer: Consumer, now) -> Job | None:
    """The job this consumer already holds, else its oldest queued job, claimed with a conditional update
    so two polls can't both take it."""
    held = db.scalar(
        select(Job).where(Job.consumer_id == consumer.id, Job.status.in_(HELD)).order_by(Job.claimed_at)
    )
    if held is not None:
        return held
    queued = db.scalars(
        select(Job.id)
        .where(Job.consumer_id == consumer.id, Job.status == "queued")
        .order_by(Job.created_at, Job.id)
    ).all()
    for job_id in queued:
        taken = db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(status="claimed", claimed_at=now, last_beat_at=now, updated_at=now)
        ).rowcount
        if taken == 1:
            consumer.busy_job_id = job_id
            job = db.get(Job, job_id)
            db.refresh(job)
            return job
    return None


## The consumer side


@router.get(
    MY_JOBS + "/next",
    response_model=JobOut,
    responses={204: {"description": "No job before `wait` ran out"}},
    **op("jobs_next", CONSUMER, "execution", mcp=False),
)
def jobs_next(
    wait: int = Query(0, ge=0, le=MAX_WAIT),
    cc: ConsumerContext = Depends(get_consumer_context),
    db: Session = Depends(get_db),
):
    """Long-poll for this consumer's next job, up to `wait` seconds; 204 when none came. A job the consumer
    already holds comes back again. Each wait holds one server worker thread, so N waiting consumers hold
    N."""
    consumer_id, org_id = cc.consumer.id, cc.consumer.org_id
    deadline = _clock() + wait
    while True:
        now = utcnow()
        stall_check(db, org_id, now)
        consumer = db.get(Consumer, consumer_id)
        job = claim(db, consumer, now)
        # Ending the transaction on every poll is what lets the next poll see jobs queued meanwhile.
        db.commit()
        if job is not None:
            return job_out(job)
        if _clock() >= deadline:
            return Response(status_code=204)
        _sleep(1)


@router.post(
    MY_JOBS + "/{id}/state",
    response_model=JobReportOut,
    **op("jobs_report", CONSUMER, "execution", mcp=False),
)
def jobs_report(
    id: str,
    body: JobReportIn,
    cc: ConsumerContext = Depends(get_consumer_context),
    db: Session = Depends(get_db),
):
    """Results for the job's refs, matched to the cycle cases whose pinned version has that automation_ref,
    and its state: `running` keeps it alive, `done` or `failed` ends it. A failed job cancels the cases it
    didn't report."""
    consumer = cc.consumer
    job = db.scalar(select(Job).where(Job.id == id, Job.consumer_id == consumer.id))
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status in FINISHED:
        raise ProblemError(409, f"The job is {job.status}", code="job_finished")
    if job.status == "queued":
        raise ProblemError(409, "Claim the job with jobs_next first", code="job_not_claimed")
    now = utcnow()
    job.last_beat_at = now
    by_ref: dict[str, list[CycleCase]] = {}
    rows = db.execute(
        select(CycleCase, CaseVersion.automation_ref)
        .join(CaseVersion, CaseVersion.id == CycleCase.case_version_id)
        .where(CycleCase.job_id == job.id)
        .order_by(CycleCase.position)
    ).all()
    for row, ref in rows:
        by_ref.setdefault(ref, []).append(row)
    recorded, unmatched = 0, []
    for item in body.results:
        matched = by_ref.get(item.ref)
        if not matched:
            unmatched.append(item.ref)
            continue
        comment = to_doc("comment", MarkdownIn(markdown=item.comment) if item.comment else None)
        for row in matched:
            record(db, cc.ctx, row, "consumer", item.status, comment, item.duration_ms, [], [], [])
            recorded += 1
    if body.state == "running":
        job.status = "running"
    else:
        job.status, job.finished_at = body.state, now
        release(db, job)
        cancelled = cancel_open_cases(db, cc.ctx, job, "job failed") if body.state == "failed" else 0
        changes = {"status": [None, job.status], "recorded": recorded, "cancelled": cancelled}
        audit.record(db, cc.ctx, "job.finish", "job", job.id, changes)
    db.commit()
    return JobReportOut(job=job_out(job), recorded=recorded, unmatched=unmatched)


## The people side


@router.get(CYCLE + "/jobs", response_model=Page[JobOut], **op("jobs_list", READ, "execution"))
def jobs_list(
    id: str,
    params: PageParams = Depends(page_params),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The cycle's jobs. Stalled jobs are requeued or failed first."""
    cycle = get_cycle(db, ctx, id)
    if stall_check(db, ctx.org.id, utcnow()):
        db.commit()
    rows, cursor, total = paginate(db, select(Job).where(Job.cycle_id == cycle.id), Job.id, params)
    return Page[JobOut](items=[job_out(j) for j in rows], next_cursor=cursor, total=total)


@router.post(JOB + "/cancel", response_model=JobOut, **op("jobs_cancel", WRITE_EXECUTION, "execution"))
def jobs_cancel(
    id: str,
    ctx: OrgContext = Depends(require_scope(WRITE_EXECUTION)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Cancel a queued or held job; its untested cases get `cancel`. A consumer holding it hears so in its
    next heartbeat reply."""
    job = get_job(db, ctx, id)
    if job.status in FINISHED:
        raise ProblemError(409, f"The job is {job.status}", code="job_finished")
    before = job.status
    job.status, job.finished_at = "cancelled", utcnow()
    if before == "queued":
        job.cancel_sent_at = job.finished_at
    release(db, job)
    cancelled = cancel_open_cases(db, ctx, job, "job cancelled")
    audit.record(
        db, ctx, "job.cancel", "job", job.id, {"status": [before, "cancelled"], "cancelled": cancelled}
    )
    db.commit()
    return job_out(job)


@router.post(JOB + "/reassign", response_model=JobOut, **op("jobs_reassign", WRITE_EXECUTION, "execution"))
def jobs_reassign(
    id: str,
    body: JobReassign,
    ctx: OrgContext = Depends(require_scope(WRITE_EXECUTION)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Move a queued job, and its cases, to another online consumer whose inventory lists the job's project.
    A held job can't move until it stalls."""
    now = utcnow()
    stall_check(db, ctx.org.id, now)
    job = get_job(db, ctx, id)
    if job.status != "queued":
        raise ProblemError(409, f"Only a queued job moves; this one is {job.status}", code="job_not_queued")
    cycle = db.get(Cycle, job.cycle_id)
    (target,) = check_consumers(db, ctx.org.id, cycle.product_id, [body.consumer_id], now)
    if job.project not in rosters(db, [target.id])[target.id]:
        raise HTTPException(422, f"Consumer {target.name!r} has no project {job.project!r} in its inventory")
    before = job.consumer_id
    job.consumer_id = target.id
    for row in db.scalars(select(CycleCase).where(CycleCase.job_id == job.id)):
        row.consumer_id = target.id
    audit.record(db, ctx, "job.reassign", "job", job.id, {"consumer_id": [before, target.id]})
    db.commit()
    return job_out(job)
