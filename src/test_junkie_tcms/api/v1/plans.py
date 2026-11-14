"""Test plans: a product's ordered list of entries (a feature, or a query T3 resolves to cases)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.cases import case_key, subtree
from test_junkie_tcms.api.v1.catalog import (
    get_plan,
    get_product,
    product_features,
    require_active_product,
    rich_mode,
    rich_out,
    set_rich,
    to_doc,
)
from test_junkie_tcms.api.v1.schemas import (
    Page,
    PlanCreate,
    PlanEntriesIn,
    PlanEntriesOrder,
    PlanEntryOut,
    PlanOut,
    PlanResolved,
    PlanUpdate,
    ResolvedCase,
    RichMode,
)
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_PLANNING
from test_junkie_tcms.db.models import (
    PLAN_MOVES,
    CaseVersion,
    CaseVersionTag,
    Feature,
    PlanEntry,
    Product,
    Release,
    ReleaseFeature,
    Tag,
    TestCase,
    TestPlan,
)
from test_junkie_tcms.richtext import doc_to_md, doc_to_text

router = APIRouter(tags=["planning"])
PLANS = "/orgs/{org}/products/{product}/plans"
PLAN = "/orgs/{org}/plans/{id}"


def _entries(db: Session, plan: TestPlan) -> list[PlanEntry]:
    rows = db.scalars(select(PlanEntry).where(PlanEntry.org_id == plan.org_id, PlanEntry.plan_id == plan.id))
    return sorted(rows, key=lambda e: (e.position, e.id))


def plan_out(db: Session, plan: TestPlan, mode: RichMode) -> PlanOut:
    return PlanOut(
        id=plan.id,
        product_id=plan.product_id,
        release_id=plan.release_id,
        name=plan.name,
        description=rich_out(plan.description, mode),
        status=plan.status,
        entries=[PlanEntryOut.model_validate(e) for e in _entries(db, plan)],
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def _check_release(db: Session, ctx: OrgContext, product_id: str, release_id: str | None) -> None:
    if release_id is None:
        return
    r = db.scalar(select(Release).where(Release.org_id == ctx.org.id, Release.id == release_id))
    if r is None or r.product_id != product_id:
        raise HTTPException(422, "release_id is not a release of this product")


def _require_writable(plan: TestPlan) -> None:
    if plan.status == "archived":
        raise HTTPException(409, "plan_archived: move the plan back to active to edit it")


def _release_features(db: Session, plan: TestPlan, release_id: str) -> list[str]:
    """The release's active features of the plan's product, in feature tree order (depth first)."""
    in_release = set(
        db.scalars(
            select(ReleaseFeature.feature_id).where(
                ReleaseFeature.org_id == plan.org_id, ReleaseFeature.release_id == release_id
            )
        )
    )
    children: dict[str | None, list[Feature]] = {}
    for f in db.scalars(
        select(Feature)
        .where(Feature.org_id == plan.org_id, Feature.product_id == plan.product_id)
        .order_by(Feature.position, Feature.id)
    ):
        children.setdefault(f.parent_id, []).append(f)
    ordered: list[str] = []
    todo = list(reversed(children.get(None, [])))
    while todo:
        f = todo.pop()
        if f.id in in_release and f.archived_at is None:
            ordered.append(f.id)
        todo.extend(reversed(children.get(f.id, [])))
    return ordered


def _check_cases(db: Session, ctx: OrgContext, product_id: str, ids: list[str]) -> None:
    """422 unless every id is a case of the product; 409 when one is archived."""
    if not ids:
        return
    found = {
        c.id: c
        for c in db.scalars(select(TestCase).where(TestCase.org_id == ctx.org.id, TestCase.id.in_(ids)))
    }
    for case_id in ids:
        c = found.get(case_id)
        if c is None or c.product_id != product_id:
            raise HTTPException(422, f"case_id {case_id} is not a case of this product")
        if c.archived_at is not None:
            raise HTTPException(409, f"Case {case_id} is archived")


def _entry_changes(e: PlanEntry) -> dict:
    return {"case_id": e.case_id, "feature_id": e.feature_id, "query": e.query, "position": e.position}


def _query_cases(db: Session, org_id: str, product_id: str, q: dict) -> list[TestCase]:
    """The product's cases whose current version matches: any of `tags`, and each non-empty field list."""
    current = and_(
        CaseVersion.org_id == TestCase.org_id,
        CaseVersion.case_id == TestCase.id,
        CaseVersion.version == TestCase.current_version,
    )
    query = (
        select(TestCase)
        .join(CaseVersion, current)
        .where(TestCase.org_id == org_id, TestCase.product_id == product_id)
    )
    for field in ("priority", "type", "automation"):
        if q.get(field):
            query = query.where(getattr(CaseVersion, field).in_(q[field]))
    if q.get("tags"):
        query = query.where(
            select(CaseVersionTag.id)
            .join(Tag, Tag.id == CaseVersionTag.tag_id)
            .where(
                CaseVersionTag.case_version_id == CaseVersion.id, Tag.name.in_([t.lower() for t in q["tags"]])
            )
            .exists()
        )
    return list(db.scalars(query.order_by(TestCase.number)))


@router.get(PLANS, response_model=Page[PlanOut], **op("plans_list", READ, "planning"))
def plans_list(
    product: str,
    include_archived: bool = Query(False),
    params: PageParams = Depends(page_params),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    query = select(TestPlan).where(TestPlan.org_id == ctx.org.id, TestPlan.product_id == p.id)
    if not include_archived:
        query = query.where(TestPlan.status != "archived")
    rows, cursor = paginate(db, query, TestPlan.id, params)
    return Page[PlanOut](items=[plan_out(db, t, mode) for t in rows], next_cursor=cursor)


@router.post(PLANS, status_code=201, response_model=PlanOut, **op("plans_create", WRITE_PLANNING, "planning"))
def plans_create(
    product: str,
    body: PlanCreate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    _check_release(db, ctx, p.id, body.release_id)
    doc = to_doc("description", body.description)
    plan = TestPlan(
        org_id=ctx.org.id,
        product_id=p.id,
        release_id=body.release_id,
        name=body.name,
        description=doc,
        description_text=doc_to_text(doc),
    )
    db.add(plan)
    db.flush()
    changes = {
        "name": [None, plan.name],
        "release_id": [None, plan.release_id],
        "description": [None, doc_to_md(doc)],
    }
    audit.record(db, ctx, "plan.create", "plan", plan.id, changes)
    db.commit()
    return plan_out(db, plan, mode)


@router.get(PLAN, response_model=PlanOut, **op("plans_get", READ, "planning"))
def plans_get(
    id: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    return plan_out(db, get_plan(db, ctx, id), mode)


@router.patch(PLAN, response_model=PlanOut, **op("plans_update", WRITE_PLANNING, "planning"))
def plans_update(
    id: str,
    body: PlanUpdate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    db: Session = Depends(get_db),
):
    """`status` moves draft → active → archived, or archived → active; any other move is 409. An archived
    plan is read-only until it moves back to active."""
    plan = get_plan(db, ctx, id)
    was_archived = plan.status == "archived"
    if (
        body.status is not None
        and body.status != plan.status
        and (plan.status, body.status) not in PLAN_MOVES
    ):
        raise HTTPException(
            409, f"invalid_status_move: a plan can't move from {plan.status} to {body.status}"
        )
    changes: dict[str, list] = {}
    if "release_id" in body.model_fields_set and body.release_id != plan.release_id:
        _check_release(db, ctx, plan.product_id, body.release_id)
        changes["release_id"] = [plan.release_id, body.release_id]
        plan.release_id = body.release_id
    for field in ("name", "status"):
        value = getattr(body, field)
        if value is not None and value != getattr(plan, field):
            changes[field] = [getattr(plan, field), value]
            setattr(plan, field, value)
    if body.description is not None:
        set_rich(plan, "description", body.description, changes)
    if was_archived and plan.status == "archived" and changes:
        db.rollback()
        raise HTTPException(409, "plan_archived: move the plan back to active to edit it")
    if changes:
        audit.record(db, ctx, "plan.update", "plan", plan.id, changes)
        db.commit()
    return plan_out(db, plan, mode)


@router.post(PLAN + "/entries", response_model=PlanOut, **op("plans_add_entries", WRITE_PLANNING, "planning"))
def plans_add_entries(
    id: str,
    body: PlanEntriesIn,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Appends entries in order: `{case_id}` (a live case of the plan's product), `{feature_id}` (an active
    feature of it), `{query}`, or `{release_id}` (a release of the product).

    A release expands now to one feature entry per feature of the release, in feature tree order, skipping
    features the plan (or this request) already has and archived ones. The release id isn't stored, so a
    later change to the release doesn't change the plan. Nothing new to add returns the plan unchanged."""
    plan = get_plan(db, ctx, id)
    _require_writable(plan)
    for i, entry in enumerate(body.entries):
        if sum(x is not None for x in (entry.case_id, entry.feature_id, entry.query, entry.release_id)) != 1:
            raise HTTPException(
                422, f"entries[{i}]: give exactly one of case_id, feature_id, query or release_id"
            )
    product_features(db, ctx, plan.product_id, [e.feature_id for e in body.entries if e.feature_id])
    _check_cases(db, ctx, plan.product_id, [e.case_id for e in body.entries if e.case_id])
    release_ids = list(dict.fromkeys(e.release_id for e in body.entries if e.release_id))
    for release_id in release_ids:
        _check_release(db, ctx, plan.product_id, release_id)
    current = _entries(db, plan)
    has = {e.feature_id for e in current if e.feature_id}
    targets: list[dict] = []
    for e in body.entries:
        if e.release_id:
            for feature_id in _release_features(db, plan, e.release_id):
                if feature_id not in has:
                    has.add(feature_id)
                    targets.append({"feature_id": feature_id})
        else:
            if e.feature_id:
                has.add(e.feature_id)
            targets.append(
                {
                    "case_id": e.case_id,
                    "feature_id": e.feature_id,
                    "query": e.query.model_dump() if e.query else None,
                }
            )
    if not targets:
        return plan_out(db, plan, mode)
    added = [
        PlanEntry(org_id=plan.org_id, plan_id=plan.id, position=len(current) + i, **t)
        for i, t in enumerate(targets)
    ]
    db.add_all(added)
    db.flush()
    changes: dict[str, list] = {"entries": [None, [_entry_changes(e) for e in added]]}
    if release_ids:
        changes["release_ids"] = [None, release_ids]
    audit.record(db, ctx, "plan.add_entries", "plan", plan.id, changes)
    db.commit()
    return plan_out(db, plan, mode)


@router.delete(
    PLAN + "/entries/{entry_id}",
    response_model=PlanOut,
    **op("plans_remove_entry", WRITE_PLANNING, "planning"),
)
def plans_remove_entry(
    id: str,
    entry_id: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    db: Session = Depends(get_db),
):
    """Removes one entry; the ones after it move up, so positions stay 0..n."""
    plan = get_plan(db, ctx, id)
    _require_writable(plan)
    entries = _entries(db, plan)
    entry = next((e for e in entries if e.id == entry_id), None)
    if entry is None:
        raise HTTPException(404, "Plan entry not found")
    db.delete(entry)
    for i, e in enumerate(e for e in entries if e.id != entry_id):
        e.position = i
    audit.record(db, ctx, "plan.remove_entry", "plan", plan.id, {"entry": [_entry_changes(entry), None]})
    db.commit()
    return plan_out(db, plan, mode)


@router.put(
    PLAN + "/entries/order",
    response_model=PlanOut,
    **op("plans_reorder_entries", WRITE_PLANNING, "planning"),
)
def plans_reorder_entries(
    id: str,
    body: PlanEntriesOrder,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_PLANNING)),
    db: Session = Depends(get_db),
):
    """Sets the entry order. `entry_ids` must be exactly the plan's current entry ids, else 409: the client
    refetches the plan and tries again."""
    plan = get_plan(db, ctx, id)
    _require_writable(plan)
    entries = _entries(db, plan)
    old = [e.id for e in entries]
    if len(body.entry_ids) != len(old) or set(body.entry_ids) != set(old):
        raise HTTPException(409, "entries_changed: entry_ids must be the plan's current entry ids, each once")
    if body.entry_ids != old:
        by_id = {e.id: e for e in entries}
        for i, entry_id in enumerate(body.entry_ids):
            by_id[entry_id].position = i
        audit.record(db, ctx, "plan.reorder_entries", "plan", plan.id, {"order": [old, body.entry_ids]})
        db.commit()
    return plan_out(db, plan, mode)


@router.get(PLAN + "/resolve", response_model=PlanResolved, **op("plans_resolve", READ, "planning"))
def plans_resolve(
    id: str,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The plan's cases in entry order, each once (its first entry wins), at their current version. Archived
    and `deprecated` cases are left out."""
    plan = get_plan(db, ctx, id)
    product = db.get(Product, plan.product_id)
    cases = {
        c.id: c
        for c in db.scalars(
            select(TestCase).where(TestCase.org_id == plan.org_id, TestCase.product_id == product.id)
        )
    }
    by_feature: dict[str, list[TestCase]] = {}
    for c in sorted(cases.values(), key=lambda c: c.number):
        by_feature.setdefault(c.feature_id, []).append(c)
    ordered: dict[str, TestCase] = {}
    for e in _entries(db, plan):
        if e.case_id is not None:
            found = [cases[e.case_id]] if e.case_id in cases else []
        elif e.feature_id is not None:
            features = subtree(db, plan.org_id, product.id, [e.feature_id])
            found = sorted((c for f in features for c in by_feature.get(f, [])), key=lambda c: c.number)
        else:
            found = _query_cases(db, plan.org_id, product.id, e.query or {})
        for c in found:
            if c.archived_at is None and c.status != "deprecated":
                ordered.setdefault(c.id, c)
    titles = dict(
        db.execute(
            select(CaseVersion.case_id, CaseVersion.title)
            .join(
                TestCase,
                and_(
                    CaseVersion.org_id == TestCase.org_id,
                    CaseVersion.case_id == TestCase.id,
                    CaseVersion.version == TestCase.current_version,
                ),
            )
            .where(TestCase.id.in_(list(ordered)))
        ).all()
    )
    items = [
        ResolvedCase(id=c.id, key=case_key(product, c), version=c.current_version, title=titles[c.id])
        for c in ordered.values()
    ]
    return PlanResolved(plan_id=plan.id, items=items)
