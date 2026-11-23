"""Cycles: a run of cases, each pinned to the case version it runs; and bulk cycles for a release."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.selection import feature_candidates, plan_candidates, product_cases, split
from test_junkie_tcms.api.v1.cases import _steps_out, case_key, db_current, resolve_cases
from test_junkie_tcms.api.v1.catalog import (
    _get,
    get_plan,
    get_product,
    get_release,
    product_features,
    require_active_product,
    rich_mode,
)
from test_junkie_tcms.api.v1.execution_schemas import (
    BulkCycleCreate,
    CycleBatchOut,
    CycleCaseAssign,
    CycleCaseOut,
    CycleCasesAdd,
    CycleCasesAdded,
    CycleCaseStatus,
    CycleCreate,
    CycleOut,
    CyclePreviewOut,
    CycleSource,
    CycleUpdate,
    PreviewConsumer,
    PreviewFeature,
    PreviewRunners,
)
from test_junkie_tcms.api.v1.job_queue import Split, check_consumers, make_jobs, split_by_runner
from test_junkie_tcms.api.v1.plans import _release_features
from test_junkie_tcms.api.v1.schemas import Page, RichMode
from test_junkie_tcms.auth.deps import OrgContext, effective_role, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_PLANNING
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import (
    CYCLE_CASE_STATUSES,
    Actor,
    CaseVersion,
    Consumer,
    Cycle,
    CycleBatch,
    CycleCase,
    Feature,
    Product,
    Release,
    Result,
    TestCase,
    TestPlan,
)
from test_junkie_tcms.errors import ProblemError

router = APIRouter(tags=["execution"])
CYCLES = "/orgs/{org}/products/{product}/cycles"
CYCLE = "/orgs/{org}/cycles/{id}"
CYCLE_CASE = "/orgs/{org}/cycle-cases/{id}"


## Lookups and checks


def get_cycle(db: Session, ctx: OrgContext, id_: str) -> Cycle:
    return _get(db, ctx, Cycle, id_, "Cycle")


def get_cycle_case(db: Session, ctx: OrgContext, id_: str) -> tuple[CycleCase, Cycle]:
    cc = db.scalar(select(CycleCase).where(CycleCase.org_id == ctx.org.id, CycleCase.id == id_))
    cycle = cc and db.get(Cycle, cc.cycle_id)
    if cc is None or not ctx.sees_product(cycle.product_id):
        raise HTTPException(404, "Cycle case not found")
    return cc, cycle


def require_open(cycle: Cycle) -> None:
    if cycle.status != "open":
        raise ProblemError(409, "The cycle is closed; reopen it first", code="cycle_closed")


def check_actor(db: Session, ctx: OrgContext, actor_id: str | None) -> None:
    """422 unless the actor is an enabled member or agent of this org."""
    if actor_id is None:
        return
    actor = db.scalar(select(Actor).where(Actor.org_id == ctx.org.id, Actor.id == actor_id))
    if actor is None or effective_role(db, actor) is None:
        raise HTTPException(422, "assignee is not an active member of this org")


def check_release(db: Session, ctx: OrgContext, product_id: str, release_id: str | None) -> None:
    if release_id is None:
        return
    r = db.scalar(select(Release).where(Release.org_id == ctx.org.id, Release.id == release_id))
    if r is None or r.product_id != product_id:
        raise HTTPException(422, "release_id is not a release of this product")
    if r.status == "cancelled":
        raise HTTPException(409, "The release is cancelled")


def require_active_plan(plan: TestPlan) -> None:
    if plan.status != "active":
        raise ProblemError(
            409,
            f"Plan {plan.name!r} is {plan.status}; only an active plan starts a cycle",
            code="plan_not_active",
        )


def resolve_source(
    db: Session, ctx: OrgContext, product: Product, body: CycleSource
) -> tuple[list[TestCase], TestPlan | None]:
    """The source's cases in run order, before `split`, and the plan when the source is one."""
    given = [f for f in ("product_id", "plan_id", "feature_ids", "case_ids") if getattr(body, f) is not None]
    if len(given) > 1:
        raise HTTPException(422, f"Give one source, not {' and '.join(given)}")
    if body.product_id is not None:
        if body.product_id != product.id:
            raise HTTPException(422, "product_id must be this product")
        return product_cases(db, ctx.org.id, product.id), None
    if body.plan_id is not None:
        plan = get_plan(db, ctx, body.plan_id)
        if plan.product_id != product.id:
            raise HTTPException(422, "plan_id is not a plan of this product")
        require_active_plan(plan)
        return plan_candidates(db, plan), plan
    if body.feature_ids is not None:
        product_features(db, ctx, product.id, body.feature_ids)
        return feature_candidates(db, ctx.org.id, product.id, body.feature_ids), None
    if body.case_ids is not None:
        found = resolve_cases(db, ctx, product, list(dict.fromkeys(body.case_ids)))
        # A key and the id of the same case pin it once.
        return list({c.id: c for c in found.values()}.values()), None
    return [], None


def pin(db: Session, cycle: Cycle, cases: list[TestCase]) -> list[CycleCase]:
    """Add each case at its current version, after the cycle's last position."""
    last = db.scalar(select(func.max(CycleCase.position)).where(CycleCase.cycle_id == cycle.id))
    rows = []
    for i, case in enumerate(cases, start=(last or 0) + 1):
        v = db_current(db, case)
        rows.append(
            CycleCase(
                org_id=cycle.org_id,
                cycle_id=cycle.id,
                case_id=case.id,
                case_version_id=v.id,
                case_version=v.version,
                assignee_actor_id=cycle.default_assignee_actor_id,
                position=i,
            )
        )
    db.add_all(rows)
    return rows


def chosen_consumers(db: Session, ctx: OrgContext, product_id: str, body: CycleSource) -> list[Consumer]:
    """The consumers an automated or both cycle runs on; none for a manual one."""
    if body.mode == "manual":
        if body.consumer_ids:
            raise HTTPException(422, "consumer_ids need mode automated or both")
        return []
    if not body.consumer_ids:
        raise HTTPException(422, f"mode {body.mode} needs at least one consumer_id")
    return check_consumers(db, ctx.org.id, product_id, body.consumer_ids, utcnow())


def new_cycle(db: Session, ctx: OrgContext, product_id: str, name: str, **fields) -> Cycle:
    cycle = Cycle(
        org_id=ctx.org.id,
        product_id=product_id,
        name=name[:200],
        status="open",
        started_at=utcnow(),
        created_by_actor_id=ctx.actor.id,
        **fields,
    )
    db.add(cycle)
    db.flush()
    return cycle


## Responses


def counts(db: Session, cycle_ids: list[str]) -> dict[str, dict[str, int]]:
    out = {i: dict.fromkeys(CYCLE_CASE_STATUSES, 0) for i in cycle_ids}
    if cycle_ids:
        rows = db.execute(
            select(CycleCase.cycle_id, CycleCase.status, func.count())
            .where(CycleCase.cycle_id.in_(cycle_ids))
            .group_by(CycleCase.cycle_id, CycleCase.status)
        )
        for cycle_id, status, n in rows:
            out[cycle_id][status] = n
    return out


def cycles_out(db: Session, cycles: list[Cycle]) -> list[CycleOut]:
    by_id = counts(db, [c.id for c in cycles])
    fields = [f for f in CycleOut.model_fields if f != "counts"]
    return [CycleOut(**{f: getattr(c, f) for f in fields}, counts=by_id[c.id]) for c in cycles]


def cycle_out(db: Session, cycle: Cycle) -> CycleOut:
    return cycles_out(db, [cycle])[0]


def cycle_cases_out(db: Session, rows: list[CycleCase], mode: RichMode) -> list[CycleCaseOut]:
    if not rows:
        return []
    cases = {c.id: c for c in db.scalars(select(TestCase).where(TestCase.id.in_({r.case_id for r in rows})))}
    versions = {
        v.id: v
        for v in db.scalars(select(CaseVersion).where(CaseVersion.id.in_({r.case_version_id for r in rows})))
    }
    products = {
        p.id: p
        for p in db.scalars(select(Product).where(Product.id.in_({c.product_id for c in cases.values()})))
    }
    out = []
    for r in rows:
        case, v = cases[r.case_id], versions[r.case_version_id]
        out.append(
            CycleCaseOut(
                id=r.id,
                cycle_id=r.cycle_id,
                case_id=r.case_id,
                key=case_key(products[case.product_id], case),
                case_version=r.case_version,
                current_version=case.current_version,
                status=r.status,
                assignee_actor_id=r.assignee_actor_id,
                runner=r.runner,
                consumer_id=r.consumer_id,
                position=r.position,
                last_result_at=r.last_result_at,
                title=v.title,
                steps=_steps_out(v.steps, mode),
            )
        )
    return out


## Cycles


@router.get(CYCLES, response_model=Page[CycleOut], **op("cycles_list", READ, "execution"))
def cycles_list(
    product: str,
    status: str | None = Query(None, pattern="^(open|closed)$"),
    params: PageParams = Depends(page_params),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    query = select(Cycle).where(Cycle.org_id == ctx.org.id, Cycle.product_id == p.id)
    if status:
        query = query.where(Cycle.status == status)
    rows, cursor, total = paginate(db, query, Cycle.id, params)
    return Page[CycleOut](items=cycles_out(db, rows), next_cursor=cursor, total=total)


@router.post(
    CYCLES, status_code=201, response_model=CycleOut, **op("cycles_create", WRITE_PLANNING, "planning")
)
def cycles_create(
    product: str,
    body: CycleCreate,
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """A cycle from at most one source: `product_id` (every live case), an active `plan_id`, `feature_ids`
    (with their sub-features) or `case_ids`; none makes an empty cycle. Archived and deprecated cases are
    left out. Each case is pinned to its current version: a later edit doesn't change this cycle."""
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    found, plan = resolve_source(db, ctx, p, body)
    release_id = body.release_id or (plan.release_id if plan else None)
    check_release(db, ctx, p.id, release_id)
    check_actor(db, ctx, body.default_assignee_actor_id)
    consumers = chosen_consumers(db, ctx, p.id, body)
    cycle = new_cycle(
        db,
        ctx,
        p.id,
        body.name,
        release_id=release_id,
        plan_id=plan.id if plan else None,
        environment=body.environment,
        default_assignee_actor_id=body.default_assignee_actor_id,
        mode=body.mode,
    )
    live, skipped = split(found)
    rows = pin(db, cycle, live)
    jobs = []
    if consumers:
        db.flush()
        versions = [(r, db.get(CaseVersion, r.case_version_id)) for r in rows]
        jobs = make_jobs(db, cycle, split_by_runner(db, consumers, versions))
    changes = {
        "name": [None, cycle.name],
        "release_id": [None, release_id],
        "plan_id": [None, cycle.plan_id],
        "cases": [None, len(live)],
        "mode": [None, cycle.mode],
        "jobs": [None, len(jobs)],
    }
    audit.record(db, ctx, "cycle.create", "cycle", cycle.id, changes)
    db.commit()
    return cycle_out(db, cycle)


@router.post(CYCLES + "/preview", response_model=CyclePreviewOut, **op("cycles_preview", READ, "planning"))
def cycles_preview(
    product: str,
    body: CycleSource,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """What `cycles_create` would pin for this source, per feature and per runner; writes nothing."""
    p = get_product(db, ctx, product)
    found, _ = resolve_source(db, ctx, p, body)
    consumers = chosen_consumers(db, ctx, p.id, body)
    live, skipped = split(found)
    per: dict[str, int] = {}
    for c in live:
        per[c.feature_id] = per.get(c.feature_id, 0) + 1
    names = dict(db.execute(select(Feature.id, Feature.name).where(Feature.id.in_(per))).all()) if per else {}
    features = [PreviewFeature(feature_id=f, name=names.get(f, ""), cases=n) for f, n in per.items()]
    plan = (
        split_by_runner(db, consumers, [(c, db_current(db, c)) for c in live])
        if consumers
        else Split(person=live)
    )
    by_consumer = [
        PreviewConsumer(
            consumer_id=c.id,
            name=c.name,
            cases=sum(len(rows) for (cid, _), rows in plan.shares.items() if cid == c.id),
            jobs=sum(1 for cid, _ in plan.shares if cid == c.id),
        )
        for c in consumers
    ]
    return CyclePreviewOut(
        total=len(live),
        features=features,
        skipped=skipped,
        runners=PreviewRunners(person=len(plan.person), consumers=by_consumer),
        unmatched=plan.unmatched,
    )


@router.get(CYCLE, response_model=CycleOut, **op("cycles_get", READ, "execution"))
def cycles_get(id: str, ctx: OrgContext = Depends(require_scope(READ)), db: Session = Depends(get_db)):
    return cycle_out(db, get_cycle(db, ctx, id))


@router.patch(CYCLE, response_model=CycleOut, **op("cycles_update", WRITE_PLANNING, "planning"))
def cycles_update(
    id: str,
    body: CycleUpdate,
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    db: Session = Depends(get_db),
):
    cycle = get_cycle(db, ctx, id)
    changes: dict[str, list] = {}
    for field in ("name", "environment", "default_assignee_actor_id"):
        if field in body.model_fields_set and getattr(body, field) != getattr(cycle, field):
            if field == "name" and body.name is None:
                raise HTTPException(422, "name can't be null")
            if field == "default_assignee_actor_id":
                check_actor(db, ctx, body.default_assignee_actor_id)
            changes[field] = [getattr(cycle, field), getattr(body, field)]
            setattr(cycle, field, getattr(body, field))
    if changes:
        audit.record(db, ctx, "cycle.update", "cycle", cycle.id, changes)
        db.commit()
    return cycle_out(db, cycle)


def _set_status(db: Session, ctx: OrgContext, id_: str, status: str) -> CycleOut:
    cycle = get_cycle(db, ctx, id_)
    if cycle.status != status:
        changes = {"status": [cycle.status, status]}
        cycle.status = status
        cycle.closed_at = utcnow() if status == "closed" else None
        audit.record(
            db, ctx, "cycle.close" if status == "closed" else "cycle.reopen", "cycle", cycle.id, changes
        )
        db.commit()
    return cycle_out(db, cycle)


@router.post(CYCLE + "/close", response_model=CycleOut, **op("cycles_close", WRITE_PLANNING, "planning"))
def cycles_close(
    id: str,
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Closes the cycle: no more results or cases until it reopens. Closing a closed cycle is a no-op."""
    return _set_status(db, ctx, id, "closed")


@router.post(CYCLE + "/reopen", response_model=CycleOut, **op("cycles_reopen", WRITE_PLANNING, "planning"))
def cycles_reopen(
    id: str,
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    return _set_status(db, ctx, id, "open")


## Cycle cases


@router.get(CYCLE + "/cases", response_model=Page[CycleCaseOut], **op("cycle_cases_list", READ, "execution"))
def cycle_cases_list(
    id: str,
    status: CycleCaseStatus | None = Query(None),
    assignee: str | None = Query(None, description="An actor id"),
    params: PageParams = Depends(page_params),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The cycle's cases with the title and steps of the version each one is pinned to."""
    cycle = get_cycle(db, ctx, id)
    query = select(CycleCase).where(CycleCase.org_id == ctx.org.id, CycleCase.cycle_id == cycle.id)
    if status:
        query = query.where(CycleCase.status == status)
    if assignee:
        query = query.where(CycleCase.assignee_actor_id == assignee)
    rows, cursor, total = paginate(db, query, CycleCase.id, params)
    return Page[CycleCaseOut](items=cycle_cases_out(db, rows, mode), next_cursor=cursor, total=total)


@router.post(
    CYCLE + "/cases", response_model=CycleCasesAdded, **op("cycle_cases_add", WRITE_PLANNING, "planning")
)
def cycle_cases_add(
    id: str,
    body: CycleCasesAdd,
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Adds live cases (each a case key like PAY-12, or an id) at their current version; a case already in the
    cycle is listed, not added again."""
    cycle = get_cycle(db, ctx, id)
    require_open(cycle)
    found, _ = resolve_source(db, ctx, db.get(Product, cycle.product_id), CycleSource(case_ids=body.case_ids))
    for c in found:
        if c.archived_at is not None:
            raise HTTPException(409, f"Case {c.id} is archived")
    present = set(db.scalars(select(CycleCase.case_id).where(CycleCase.cycle_id == cycle.id)))
    new = [c for c in found if c.id not in present]
    pin(db, cycle, new)
    if new:
        audit.record(db, ctx, "cycle_case.add", "cycle", cycle.id, {"case_ids": [None, [c.id for c in new]]})
    db.commit()
    return CycleCasesAdded(
        added=[c.id for c in new], already_present=[c.id for c in found if c.id in present]
    )


@router.post(
    CYCLE_CASE + "/assign",
    response_model=CycleCaseOut,
    **op("cycle_cases_assign", WRITE_PLANNING, "planning"),
)
def cycle_cases_assign(
    id: str,
    body: CycleCaseAssign,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    cc, cycle = get_cycle_case(db, ctx, id)
    require_open(cycle)
    check_actor(db, ctx, body.assignee_actor_id)
    if cc.assignee_actor_id != body.assignee_actor_id:
        changes = {"assignee_actor_id": [cc.assignee_actor_id, body.assignee_actor_id]}
        cc.assignee_actor_id = body.assignee_actor_id
        audit.record(db, ctx, "cycle_case.assign", "cycle_case", cc.id, changes)
        db.commit()
    return cycle_cases_out(db, [cc], mode)[0]


@router.post(
    CYCLE_CASE + "/refresh-version",
    response_model=CycleCaseOut,
    **op("cycle_cases_refresh_version", WRITE_PLANNING, "planning"),
)
def cycle_cases_refresh_version(
    id: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Re-pins the case to its current version, only while it has no result (409 once one is recorded)."""
    cc, cycle = get_cycle_case(db, ctx, id)
    require_open(cycle)
    if db.scalar(select(Result.id).where(Result.cycle_case_id == cc.id).limit(1)):
        raise ProblemError(409, "The case already has a result in this cycle", code="has_results")
    v = db_current(db, db.get(TestCase, cc.case_id))
    if v.id != cc.case_version_id:
        changes = {"case_version": [cc.case_version, v.version]}
        cc.case_version_id, cc.case_version = v.id, v.version
        audit.record(db, ctx, "cycle_case.refresh_version", "cycle_case", cc.id, changes)
        db.commit()
    return cycle_cases_out(db, [cc], mode)[0]


## Bulk cycles for a release


def _nearest(case_feature: str, affected: set[str], parents: dict[str, str | None]) -> str | None:
    """The nearest affected feature at or above the case's own, walking up through archived ones too."""
    f: str | None = case_feature
    while f is not None:
        if f in affected:
            return f
        f = parents.get(f)
    return None


@router.post(
    "/orgs/{org}/releases/{id}/cycles/bulk",
    status_code=201,
    response_model=CycleBatchOut,
    **op("cycles_bulk_create", WRITE_PLANNING, "planning"),
)
def cycles_bulk_create(
    id: str,
    body: BulkCycleCreate,
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Pick a release: `features` makes one cycle per affected (non-archived) feature, each case in the
    cycle of its nearest affected feature; `plans` makes one cycle per active plan of the release (or per
    listed plan). All the cycles share one batch, and the call makes all or none of them."""
    release = get_release(db, ctx, id)
    require_active_product(db, release.product_id)
    if release.status == "cancelled":
        raise HTTPException(409, "The release is cancelled")
    label = body.name or release.version
    batch = CycleBatch(
        org_id=ctx.org.id,
        product_id=release.product_id,
        release_id=release.id,
        name=label,
        mode=body.mode,
        environment=body.environment,
        created_by_actor_id=ctx.actor.id,
    )
    db.add(batch)
    db.flush()
    common = {"release_id": release.id, "batch_id": batch.id, "environment": body.environment}
    cycles: list[Cycle] = []
    if body.mode == "features":
        if body.plan_ids:
            raise HTTPException(422, "plan_ids is for mode plans")
        # _release_features reads org_id and product_id, which a release has like a plan.
        affected = _release_features(db, release, release.id)
        if not affected:
            raise HTTPException(422, "The release lists no active features")
        features = {
            f.id: f
            for f in db.scalars(
                select(Feature).where(Feature.org_id == ctx.org.id, Feature.product_id == release.product_id)
            )
        }
        parents = {f.id: f.parent_id for f in features.values()}
        live, _ = split(product_cases(db, ctx.org.id, release.product_id))
        owned: dict[str, list[TestCase]] = {f: [] for f in affected}
        for c in live:
            owner = _nearest(c.feature_id, set(affected), parents)
            if owner is not None:
                owned[owner].append(c)
        for f in affected:
            cycle = new_cycle(
                db, ctx, release.product_id, f"{label} · {features[f].name}", feature_id=f, **common
            )
            pin(db, cycle, owned[f])
            cycles.append(cycle)
    else:
        if body.plan_ids:
            plans = [get_plan(db, ctx, p) for p in dict.fromkeys(body.plan_ids)]
            for plan in plans:
                if plan.product_id != release.product_id:
                    raise HTTPException(422, f"Plan {plan.id} is not a plan of this release's product")
                require_active_plan(plan)
        else:
            plans = list(
                db.scalars(
                    select(TestPlan)
                    .where(
                        TestPlan.org_id == ctx.org.id,
                        TestPlan.release_id == release.id,
                        TestPlan.status == "active",
                    )
                    .order_by(TestPlan.id)
                )
            )
            if not plans:
                raise HTTPException(422, "The release has no active plans")
        for plan in plans:
            cycle = new_cycle(
                db, ctx, release.product_id, f"{label} · {plan.name}", plan_id=plan.id, **common
            )
            pin(db, cycle, split(plan_candidates(db, plan))[0])
            cycles.append(cycle)
    changes = {"release_id": [None, release.id], "mode": [None, body.mode], "cycles": [None, len(cycles)]}
    audit.record(db, ctx, "cycle_batch.create", "cycle_batch", batch.id, changes)
    db.commit()
    return batch_out(db, batch)


def batch_out(db: Session, batch: CycleBatch) -> CycleBatchOut:
    cycles = list(db.scalars(select(Cycle).where(Cycle.batch_id == batch.id).order_by(Cycle.id)))
    fields = [f for f in CycleBatchOut.model_fields if f != "cycles"]
    return CycleBatchOut(**{f: getattr(batch, f) for f in fields}, cycles=cycles_out(db, cycles))


@router.get(
    "/orgs/{org}/cycle-batches/{id}",
    response_model=CycleBatchOut,
    **op("cycle_batches_get", READ, "planning"),
)
def cycle_batches_get(id: str, ctx: OrgContext = Depends(require_scope(READ)), db: Session = Depends(get_db)):
    return batch_out(db, _get(db, ctx, CycleBatch, id, "Cycle batch"))
