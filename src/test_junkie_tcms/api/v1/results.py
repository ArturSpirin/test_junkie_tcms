"""Results: append-only attempts on a cycle case, with per-step status, attachments and defects."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.cases import case_key
from test_junkie_tcms.api.v1.catalog import rich_mode, rich_out, to_doc
from test_junkie_tcms.api.v1.cycles import CYCLE, CYCLE_CASE, get_cycle, get_cycle_case, require_open
from test_junkie_tcms.api.v1.execution_schemas import (
    BulkResultRow,
    BulkResultsIn,
    BulkResultsOut,
    BulkUnmatched,
    CycleBuildOut,
    ResultCreate,
    ResultOut,
    StepResultOut,
)
from test_junkie_tcms.api.v1.schemas import Page, RichMode
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_EXECUTION
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import (
    Attachment,
    CaseVersion,
    Cycle,
    CycleCase,
    Product,
    Result,
    ResultAttachment,
    TestCase,
)
from test_junkie_tcms.errors import ProblemError
from test_junkie_tcms.richtext import doc_to_text

router = APIRouter(tags=["execution"])
MAX_BUILDS = 20


def result_via(request: Request, ctx: OrgContext) -> str:
    # "mcp" comes from the ASGI scope marker the MCP dispatcher sets (auth/deps.py), never from a client
    # header, so the label can't be claimed by a plain API call.
    return ctx.principal.via


def check_attachments(db: Session, ctx: OrgContext, cycle: Cycle, ids: set[str]) -> None:
    if not ids:
        return
    found = set(
        db.scalars(
            select(Attachment.id).where(
                Attachment.org_id == ctx.org.id,
                Attachment.product_id == cycle.product_id,
                Attachment.id.in_(ids),
            )
        )
    )
    missing = sorted(ids - found)
    if missing:
        raise HTTPException(422, f"attachment {missing[0]} is not an attachment of this product")


def record(
    db: Session,
    ctx: OrgContext,
    cc: CycleCase,
    via: str,
    status: str,
    comment: dict[str, Any],
    duration_ms: int | None,
    steps: list[dict[str, Any]],
    attachment_ids: list[str],
    defects: list[dict[str, Any]],
    skip_reason: str | None = None,
    build: str | None = None,
) -> Result:
    """Append the next attempt and move the cycle case to its status."""
    last = db.scalar(select(func.max(Result.attempt)).where(Result.cycle_case_id == cc.id))
    now = utcnow()
    result = Result(
        org_id=ctx.org.id,
        cycle_case_id=cc.id,
        attempt=(last or 0) + 1,
        case_version=cc.case_version,
        status=status,
        actor_id=ctx.actor.id,
        via=via,
        comment=comment,
        comment_text=doc_to_text(comment),
        duration_ms=duration_ms,
        steps=steps,
        attachment_ids=attachment_ids,
        defects=defects,
        skip_reason=skip_reason,
        build=build,
        at=now,
    )
    db.add(result)
    db.flush()
    every = dict.fromkeys(attachment_ids + [a for s in steps for a in s["attachment_ids"]])
    db.add_all(ResultAttachment(org_id=ctx.org.id, result_id=result.id, attachment_id=a) for a in every)
    cc.status, cc.last_result_at = status, now
    return result


def result_out(r: Result, mode: RichMode) -> ResultOut:
    return ResultOut(
        id=r.id,
        cycle_case_id=r.cycle_case_id,
        attempt=r.attempt,
        case_version=r.case_version,
        status=r.status,
        actor_id=r.actor_id,
        via=r.via,
        comment=rich_out(r.comment, mode),
        duration_ms=r.duration_ms,
        steps=[
            StepResultOut(
                step_id=s["step_id"],
                status=s["status"],
                actual=rich_out(s["actual"], mode),
                attachment_ids=s["attachment_ids"],
            )
            for s in r.steps
        ],
        attachment_ids=r.attachment_ids,
        defects=r.defects,
        skip_reason=r.skip_reason,
        build=r.build,
        at=r.at,
    )


def check_skip_reason(
    where: str, status: str, skip_reason: str | None, comment: dict[str, Any] | None
) -> None:
    """A skip_reason goes only with a skip, and `other` needs a comment saying what it is."""
    if skip_reason is None:
        return
    if status != "skip":
        raise ProblemError(422, f"{where}skip_reason goes only with status skip", code="skip_reason_not_skip")
    if skip_reason == "other" and not doc_to_text(comment).strip():
        raise ProblemError(422, f"{where}skip_reason other needs a comment", code="skip_reason_needs_comment")


@router.post(
    CYCLE_CASE + "/results",
    status_code=201,
    response_model=ResultOut,
    **op("results_create", WRITE_EXECUTION, "execution"),
)
def results_create(
    id: str,
    body: ResultCreate,
    request: Request,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_EXECUTION)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Records the next attempt for the case. Step ids come from the version the cycle pinned, each once.
    A `skip` needs a `skip_reason` code or a reason in `comment`. Results are never edited: a retest is the
    next attempt."""
    cc, cycle = get_cycle_case(db, ctx, id)
    require_open(cycle)
    comment = to_doc("comment", body.comment)
    check_skip_reason("", body.status, body.skip_reason, comment)
    if body.status == "skip" and body.skip_reason is None and not doc_to_text(comment).strip():
        raise ProblemError(422, "A skip needs a skip_reason or a reason in comment", code="skip_needs_reason")
    pinned = db.get(CaseVersion, cc.case_version_id)
    known = {s["id"] for s in pinned.steps}
    seen: set[str] = set()
    steps = []
    for i, s in enumerate(body.steps):
        if s.step_id not in known:
            raise HTTPException(422, f"steps[{i}].step_id is not a step of version {cc.case_version}")
        if s.step_id in seen:
            raise HTTPException(422, f"steps[{i}].step_id appears twice")
        seen.add(s.step_id)
        steps.append(
            {
                "step_id": s.step_id,
                "status": s.status,
                "actual": to_doc(f"steps[{i}].actual", s.actual),
                "attachment_ids": list(dict.fromkeys(s.attachment_ids)),
            }
        )
    attachment_ids = list(dict.fromkeys(body.attachment_ids))
    check_attachments(db, ctx, cycle, set(attachment_ids) | {a for s in steps for a in s["attachment_ids"]})
    defects = [d.model_dump(exclude_none=True) for d in body.defects]
    result = record(
        db,
        ctx,
        cc,
        result_via(request, ctx),
        body.status,
        comment,
        body.duration_ms,
        steps,
        attachment_ids,
        defects,
        body.skip_reason,
        body.build,
    )
    changes = {
        "cycle_case_id": [None, cc.id],
        "attempt": [None, result.attempt],
        "status": [None, result.status],
    }
    audit.record(db, ctx, "result.create", "result", result.id, changes)
    db.commit()
    return result_out(result, mode)


@router.get(CYCLE_CASE + "/results", response_model=Page[ResultOut], **op("results_list", READ, "execution"))
def results_list(
    id: str,
    params: PageParams = Depends(page_params),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Every attempt for the cycle case, oldest first."""
    cc, _ = get_cycle_case(db, ctx, id)
    query = select(Result).where(Result.org_id == ctx.org.id, Result.cycle_case_id == cc.id)
    rows, cursor, total = paginate(db, query, Result.id, params)
    return Page[ResultOut](items=[result_out(r, mode) for r in rows], next_cursor=cursor, total=total)


@router.post(
    CYCLE + "/results/bulk",
    status_code=201,
    response_model=BulkResultsOut,
    **op("results_bulk_create", WRITE_EXECUTION, "execution"),
)
def results_bulk_create(
    id: str,
    body: BulkResultsIn,
    request: Request,
    ctx: OrgContext = Depends(require_scope(WRITE_EXECUTION)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Many results at once, each matched to a case of this cycle by `case_key` or by the pinned version's
    `automation_ref`. Items that match nothing are listed in `unmatched`; the rest are recorded."""
    cycle = get_cycle(db, ctx, id)
    require_open(cycle)
    product = db.get(Product, cycle.product_id)
    rows = list(
        db.scalars(select(CycleCase).where(CycleCase.org_id == ctx.org.id, CycleCase.cycle_id == cycle.id))
    )
    cases = {c.id: c for c in db.scalars(select(TestCase).where(TestCase.id.in_({r.case_id for r in rows})))}
    refs = dict(
        db.execute(
            select(CaseVersion.id, CaseVersion.automation_ref).where(
                CaseVersion.id.in_({r.case_version_id for r in rows})
            )
        ).all()
    )
    by_key = {case_key(product, cases[r.case_id]).upper(): r for r in rows}
    by_ref = {refs[r.case_version_id]: r for r in rows if refs.get(r.case_version_id)}
    via = result_via(request, ctx)
    created, unmatched = [], []
    for i, item in enumerate(body.items):
        if item.case_key is None and item.automation_ref is None:
            raise HTTPException(422, f"items[{i}] needs case_key or automation_ref")
        cc = by_key.get(item.case_key.upper()) if item.case_key else by_ref.get(item.automation_ref)
        if cc is None:
            unmatched.append(
                BulkUnmatched(index=i, case_key=item.case_key, automation_ref=item.automation_ref)
            )
            continue
        comment = to_doc(f"items[{i}].comment", item.comment)
        check_skip_reason(f"items[{i}].", item.status, item.skip_reason, comment)
        defects = [d.model_dump(exclude_none=True) for d in item.defects]
        result = record(
            db,
            ctx,
            cc,
            via,
            item.status,
            comment,
            item.duration_ms,
            [],
            [],
            defects,
            item.skip_reason,
            item.build,
        )
        created.append(
            BulkResultRow(index=i, cycle_case_id=cc.id, result_id=result.id, attempt=result.attempt)
        )
    if created:
        counts: dict[str, int] = {}
        for i in (r.index for r in created):
            counts[body.items[i].status] = counts.get(body.items[i].status, 0) + 1
        changes = {
            "results": [None, len(created)],
            "unmatched": [None, len(unmatched)],
            "statuses": [None, counts],
        }
        audit.record(db, ctx, "result.bulk_create", "cycle", cycle.id, changes)
    db.commit()
    return BulkResultsOut(created=created, unmatched=unmatched)


@router.get(CYCLE + "/builds", response_model=list[CycleBuildOut], **op("cycle_builds", READ, "execution"))
def cycle_builds(id: str, ctx: OrgContext = Depends(require_scope(READ)), db: Session = Depends(get_db)):
    """The builds recorded on results of the cycle's product, latest first, at most 20: the choices for
    the build under test."""
    cycle = get_cycle(db, ctx, id)
    last = func.max(Result.at)
    rows = db.execute(
        select(Result.build, last)
        .join(CycleCase, CycleCase.id == Result.cycle_case_id)
        .join(Cycle, Cycle.id == CycleCase.cycle_id)
        .where(Cycle.org_id == ctx.org.id, Cycle.product_id == cycle.product_id, Result.build.is_not(None))
        .group_by(Result.build)
        .order_by(last.desc(), Result.build)
        .limit(MAX_BUILDS)
    ).all()
    return [CycleBuildOut(build=b, last_at=at) for b, at in rows]
