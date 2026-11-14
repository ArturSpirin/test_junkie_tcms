"""Test cases and their immutable versions. Every edit of a case's content adds a version; addressed by key
(`PAY-12`) or id."""

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.if_match import if_match, stale
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.catalog import (
    get_product,
    product_features,
    require_active_product,
    rich_mode,
    rich_out,
)
from test_junkie_tcms.api.v1.catalog import to_doc as _to_doc
from test_junkie_tcms.api.v1.schemas import (
    CaseBulkIn,
    CaseBulkItem,
    CaseBulkOut,
    CaseBulkResult,
    CaseCreate,
    CaseFields,
    CaseMove,
    CaseOut,
    CaseRestore,
    CaseUpdate,
    CaseVersionOut,
    CaseVersionSummary,
    Page,
    RichMode,
    StepOut,
    TagOut,
)
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_CASES
from test_junkie_tcms.db.base import new_id, utcnow
from test_junkie_tcms.db.models import CaseVersion, CaseVersionTag, Feature, Product, Tag, TestCase
from test_junkie_tcms.richtext import doc_to_md, doc_to_text, empty_doc

router = APIRouter(tags=["cases"])
CASES = "/orgs/{org}/products/{product}/cases"
CASE = "/orgs/{org}/cases/{case}"
TAGS = "/orgs/{org}/products/{product}/tags"
CASE_KEY = re.compile(r"^([A-Z][A-Z0-9]{1,9})-(\d+)$")
TAG_NAME = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
MAX_CUSTOM = 16 * 1024
DEFAULTS: dict[str, Any] = {
    "priority": "medium",
    "type": "functional",
    "status": "draft",
    "automation": "manual",
    "automation_ref": None,
    "links": [],
    "custom": {},
    "tags": [],
}
# Versioned content kept on test_case too, so lists can filter without a join.
CASE_COLUMNS = ("status", "automation", "automation_ref")


## Lookups


def case_key(product: Product, case: TestCase) -> str:
    return f"{product.key}-{case.number}"


def get_case(db: Session, ctx: OrgContext, ref: str) -> TestCase:
    """A case by key or id; 404 when it isn't in the org or the token can't see its product."""
    m = CASE_KEY.match(ref)
    query = select(TestCase).where(TestCase.org_id == ctx.org.id)
    if m:
        query = query.join(Product, Product.id == TestCase.product_id).where(
            Product.key == m.group(1), TestCase.number == int(m.group(2))
        )
    else:
        query = query.where(TestCase.id == ref)
    case = db.scalar(query)
    if case is None or not ctx.sees_product(case.product_id):
        raise HTTPException(404, "Case not found")
    return case


def get_version(db: Session, case: TestCase, version: int) -> CaseVersion | None:
    return db.scalar(
        select(CaseVersion).where(
            CaseVersion.org_id == case.org_id, CaseVersion.case_id == case.id, CaseVersion.version == version
        )
    )


def version_tags(db: Session, version_ids: list[str]) -> dict[str, list[str]]:
    """Tag names per case_version id, sorted."""
    out: dict[str, list[str]] = {v: [] for v in version_ids}
    if not version_ids:
        return out
    rows = db.execute(
        select(CaseVersionTag.case_version_id, Tag.name)
        .join(Tag, Tag.id == CaseVersionTag.tag_id)
        .where(CaseVersionTag.case_version_id.in_(version_ids))
        .order_by(Tag.name)
    )
    for version_id, name in rows:
        out[version_id].append(name)
    return out


def subtree(db: Session, org_id: str, product_id: str, feature_ids: list[str]) -> set[str]:
    """The features and every feature under them."""
    children: dict[str | None, list[str]] = {}
    for f_id, parent in db.execute(
        select(Feature.id, Feature.parent_id).where(
            Feature.org_id == org_id, Feature.product_id == product_id
        )
    ):
        children.setdefault(parent, []).append(f_id)
    seen: set[str] = set()
    todo = list(feature_ids)
    while todo:
        f_id = todo.pop()
        if f_id not in seen:
            seen.add(f_id)
            todo.extend(children.get(f_id, []))
    return seen


## Content: what a version holds


def content_of(v: CaseVersion, tags: list[str]) -> dict[str, Any]:
    return {
        "title": v.title,
        "preconditions": v.preconditions,
        "steps": v.steps,
        "priority": v.priority,
        "type": v.type,
        "status": v.status,
        "automation": v.automation,
        "automation_ref": v.automation_ref,
        "links": v.links,
        "custom": v.custom,
        "tags": tags,
    }


def _tag_names(names: list[str]) -> list[str]:
    out = sorted({n.strip().lower() for n in names})
    bad = [n for n in out if not TAG_NAME.match(n)]
    if bad:
        raise HTTPException(
            422, f"Tag names are 1-64 of a-z, 0-9, _ . : - and start with a letter or digit: {', '.join(bad)}"
        )
    return out


def apply_fields(body: CaseFields, current: dict[str, Any]) -> dict[str, Any]:
    """The content after the body's fields go over `current`; a field left out (or null, where the
    field can't be empty) keeps its value."""
    new = dict(current)
    given = body.model_fields_set
    title = getattr(body, "title", None)
    if title is not None:
        new["title"] = title
    if body.preconditions is not None:
        new["preconditions"] = _to_doc("preconditions", body.preconditions)
    if body.steps is not None:
        known = {s["id"] for s in current["steps"]}
        steps, seen = [], set()
        for i, s in enumerate(body.steps):
            if s.id is not None and s.id not in known:
                raise HTTPException(422, f"steps[{i}].id {s.id} is not a step of the current version")
            if s.id is not None and s.id in seen:
                raise HTTPException(422, f"steps[{i}].id {s.id} appears twice")
            step_id = s.id or new_id()
            seen.add(step_id)
            steps.append(
                {
                    "id": step_id,
                    "action": _to_doc(f"steps[{i}].action", s.action),
                    "expected": _to_doc(f"steps[{i}].expected", s.expected),
                }
            )
        new["steps"] = steps
    for field in ("priority", "type", "status", "automation"):
        if getattr(body, field) is not None:
            new[field] = getattr(body, field)
    if "automation_ref" in given:
        new["automation_ref"] = body.automation_ref
    if body.links is not None:
        new["links"] = [link.model_dump() for link in body.links]
    if body.custom is not None:
        if len(json.dumps(body.custom)) > MAX_CUSTOM:
            raise HTTPException(422, "custom is over 16 KB as JSON")
        new["custom"] = body.custom
    if body.tags is not None:
        new["tags"] = _tag_names(body.tags)
    return new


def _steps_md(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"action": doc_to_md(s["action"]), "expected": doc_to_md(s["expected"])} for s in steps]


def _printable(field: str, value: Any) -> Any:
    if field == "preconditions":
        return doc_to_md(value)
    if field == "steps":
        return _steps_md(value)
    return value


def content_changes(before: dict[str, Any] | None, after: dict[str, Any]) -> dict[str, list]:
    """Audit `changes`: each field that differs, [before, after], rich fields as Markdown."""
    changes = {}
    for field, value in after.items():
        old = None if before is None else before[field]
        if before is None or old != value:
            changes[field] = [None if old is None else _printable(field, old), _printable(field, value)]
    return changes


def ensure_tags(db: Session, org_id: str, product_id: str, names: list[str]) -> list[Tag]:
    """The product's tags with these names, made on first use: a tag's product is always the case's."""
    if not names:
        return []
    found = {
        t.name: t
        for t in db.scalars(
            select(Tag).where(Tag.org_id == org_id, Tag.product_id == product_id, Tag.name.in_(names))
        )
    }
    for name in names:
        if name not in found:
            found[name] = Tag(org_id=org_id, product_id=product_id, name=name)
            db.add(found[name])
    db.flush()
    return [found[n] for n in names]


def add_version(
    db: Session,
    ctx: OrgContext,
    case: TestCase,
    number: int,
    content: dict[str, Any],
    change_note: str | None,
) -> CaseVersion:
    steps_text = "\n".join(
        part
        for s in content["steps"]
        for part in (doc_to_text(s["action"]), doc_to_text(s["expected"]))
        if part
    )
    v = CaseVersion(
        org_id=case.org_id,
        case_id=case.id,
        version=number,
        title=content["title"],
        title_text=content["title"],
        preconditions=content["preconditions"],
        preconditions_text=doc_to_text(content["preconditions"]),
        steps=content["steps"],
        steps_text=steps_text,
        priority=content["priority"],
        type=content["type"],
        status=content["status"],
        automation=content["automation"],
        automation_ref=content["automation_ref"],
        links=content["links"],
        custom=content["custom"],
        change_note=change_note,
        created_by_actor_id=ctx.actor.id,
    )
    db.add(v)
    db.flush()
    # ensure_tags finds or creates tags only in the case's product, so tag product = case product.
    for tag in ensure_tags(db, case.org_id, case.product_id, content["tags"]):
        db.add(CaseVersionTag(org_id=case.org_id, case_version_id=v.id, tag_id=tag.id))
    db.flush()
    return v


## Writes


def create_case(
    db: Session, ctx: OrgContext, product: Product, body: CaseCreate | CaseFields, feature_id: str, title: str
) -> tuple[TestCase, CaseVersion, dict[str, Any]]:
    require_active_product(db, product.id)
    product_features(db, ctx, product.id, [feature_id])
    content = apply_fields(body, {"title": title, "preconditions": empty_doc(), "steps": [], **DEFAULTS})
    content["title"] = title
    number = db.execute(
        update(Product)
        .where(Product.org_id == ctx.org.id, Product.id == product.id)
        .values(case_seq=Product.case_seq + 1)
        .returning(Product.case_seq)
    ).scalar_one()
    case = TestCase(
        org_id=ctx.org.id,
        product_id=product.id,
        feature_id=feature_id,
        number=number,
        current_version=1,
        **{c: content[c] for c in CASE_COLUMNS},
    )
    db.add(case)
    db.flush()
    v = add_version(db, ctx, case, 1, content, body.change_note)
    return case, v, content


def edit_case(
    db: Session, ctx: OrgContext, case: TestCase, expected: int, new: dict[str, Any], change_note: str | None
) -> tuple[CaseVersion | None, dict[str, list]]:
    """Add version n+1 when `new` differs from the current content; None when it doesn't. Moves
    `current_version` only from `expected`, so two writers holding the same version can't both win."""
    current = db_current(db, case)
    old = content_of(current, version_tags(db, [current.id])[current.id])
    if new == old:
        return None, {}
    n = case.current_version
    moved = db.execute(
        update(TestCase)
        .where(TestCase.org_id == case.org_id, TestCase.id == case.id, TestCase.current_version == expected)
        .values(current_version=n + 1, **{c: new[c] for c in CASE_COLUMNS})
        .execution_options(synchronize_session="fetch")
    )
    if moved.rowcount != 1:
        db.rollback()
        raise stale(db.get(TestCase, case.id, populate_existing=True).current_version)
    v = add_version(db, ctx, case, n + 1, new, change_note)
    changes = content_changes(old, new)
    changes["entity_version"] = [n, n + 1]
    return v, changes


def db_current(db: Session, case: TestCase) -> CaseVersion:
    return get_version(db, case, case.current_version)


def _check_editable(case: TestCase, expected: int) -> None:
    if case.archived_at is not None:
        raise HTTPException(409, "Case is archived")
    if expected != case.current_version:
        raise stale(case.current_version)


## Responses


def _steps_out(steps: list[dict[str, Any]], mode: RichMode) -> list[StepOut]:
    return [
        StepOut(id=s["id"], action=rich_out(s["action"], mode), expected=rich_out(s["expected"], mode))
        for s in steps
    ]


def case_out(db: Session, case: TestCase, v: CaseVersion, tags: list[str], mode: RichMode) -> CaseOut:
    product = db.get(Product, case.product_id)
    return CaseOut(
        id=case.id,
        key=case_key(product, case),
        number=case.number,
        product_id=case.product_id,
        feature_id=case.feature_id,
        current_version=case.current_version,
        title=v.title,
        preconditions=rich_out(v.preconditions, mode),
        steps=_steps_out(v.steps, mode),
        priority=v.priority,
        type=v.type,
        status=v.status,
        automation=v.automation,
        automation_ref=v.automation_ref,
        links=v.links,
        custom=v.custom,
        tags=tags,
        change_note=v.change_note,
        archived_at=case.archived_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def current_out(db: Session, case: TestCase, mode: RichMode, response: Response) -> CaseOut:
    v = db_current(db, case)
    response.headers["ETag"] = f'"{case.current_version}"'
    return case_out(db, case, v, version_tags(db, [v.id])[v.id], mode)


def version_out(db: Session, case: TestCase, v: CaseVersion, mode: RichMode) -> CaseVersionOut:
    product = db.get(Product, case.product_id)
    return CaseVersionOut(
        case_id=case.id,
        key=case_key(product, case),
        version=v.version,
        title=v.title,
        preconditions=rich_out(v.preconditions, mode),
        steps=_steps_out(v.steps, mode),
        priority=v.priority,
        type=v.type,
        status=v.status,
        automation=v.automation,
        automation_ref=v.automation_ref,
        links=v.links,
        custom=v.custom,
        tags=version_tags(db, [v.id])[v.id],
        change_note=v.change_note,
        created_by_actor_id=v.created_by_actor_id,
        created_at=v.created_at,
    )


## Routes


@router.get(CASES, response_model=Page[CaseOut], **op("cases_list", READ, "cases"))
def cases_list(
    product: str,
    feature: str | None = Query(None, description="A feature id; its subtree is included"),
    tag: list[str] = Query([], description="Repeatable; a case must have every tag"),
    q: str | None = Query(None, max_length=200, description="Case-insensitive part of the title"),
    status: list[str] = Query([]),
    automation: list[str] = Query([]),
    include_archived: bool = Query(False),
    params: PageParams = Depends(page_params),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    current = and_(
        CaseVersion.org_id == TestCase.org_id,
        CaseVersion.case_id == TestCase.id,
        CaseVersion.version == TestCase.current_version,
    )
    query = (
        select(TestCase)
        .join(CaseVersion, current)
        .where(TestCase.org_id == ctx.org.id, TestCase.product_id == p.id)
    )
    if not include_archived:
        query = query.where(TestCase.archived_at.is_(None))
    if feature is not None:
        query = query.where(TestCase.feature_id.in_(subtree(db, ctx.org.id, p.id, [feature])))
    if status:
        query = query.where(TestCase.status.in_(status))
    if automation:
        query = query.where(TestCase.automation.in_(automation))
    if q:
        query = query.where(func.lower(CaseVersion.title).contains(q.lower(), autoescape=True))
    for name in {t.strip().lower() for t in tag}:
        query = query.where(
            select(CaseVersionTag.id)
            .join(Tag, Tag.id == CaseVersionTag.tag_id)
            .where(CaseVersionTag.case_version_id == CaseVersion.id, Tag.name == name)
            .exists()
        )
    rows, cursor = paginate(db, query, TestCase.id, params)
    versions = {
        v.case_id: v
        for v in db.scalars(
            select(CaseVersion).join(TestCase, current).where(TestCase.id.in_([c.id for c in rows]))
        )
    }
    tags = version_tags(db, [v.id for v in versions.values()])
    items = [case_out(db, c, versions[c.id], tags[versions[c.id].id], mode) for c in rows]
    return Page[CaseOut](items=items, next_cursor=cursor)


@router.post(CASES, status_code=201, response_model=CaseOut, **op("cases_create", WRITE_CASES, "cases"))
def cases_create(
    product: str,
    body: CaseCreate,
    response: Response,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    case, v, content = create_case(db, ctx, p, body, body.feature_id, body.title)
    changes = content_changes(None, content)
    changes["entity_version"] = [None, 1]
    audit.record(db, ctx, "case.create", "test_case", case.id, changes)
    db.commit()
    response.headers["ETag"] = '"1"'
    response.headers["Location"] = f"/api/v1/orgs/{ctx.org.slug}/cases/{case.id}"
    return case_out(db, case, v, content["tags"], mode)


@router.get(CASE, response_model=CaseOut, **op("cases_get", READ, "cases"))
def cases_get(
    case: str,
    response: Response,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    return current_out(db, get_case(db, ctx, case), mode, response)


@router.patch(CASE, response_model=CaseOut, **op("cases_update", WRITE_CASES, "cases"))
def cases_update(
    case: str,
    body: CaseUpdate,
    response: Response,
    expected: int = Depends(if_match),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    db: Session = Depends(get_db),
):
    c = get_case(db, ctx, case)
    _check_editable(c, expected)
    current = db_current(db, c)
    new = apply_fields(body, content_of(current, version_tags(db, [current.id])[current.id]))
    _, changes = edit_case(db, ctx, c, expected, new, body.change_note)
    if changes:
        audit.record(db, ctx, "case.update", "test_case", c.id, changes)
        db.commit()
    return current_out(db, c, mode, response)


@router.get(
    CASE + "/versions", response_model=Page[CaseVersionSummary], **op("cases_versions_list", READ, "cases")
)
def cases_versions_list(
    case: str,
    params: PageParams = Depends(page_params),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Newest first; the cursor is the last version number of the previous page."""
    c = get_case(db, ctx, case)
    query = select(CaseVersion).where(CaseVersion.org_id == c.org_id, CaseVersion.case_id == c.id)
    if params.cursor:
        if not params.cursor.isdigit():
            raise HTTPException(422, "cursor must be a version number")
        query = query.where(CaseVersion.version < int(params.cursor))
    rows = list(db.scalars(query.order_by(CaseVersion.version.desc()).limit(params.limit + 1)))
    cursor = None
    if len(rows) > params.limit:
        rows = rows[: params.limit]
        cursor = str(rows[-1].version)
    items = [
        CaseVersionSummary(
            version=v.version,
            title=v.title,
            change_note=v.change_note,
            created_by_actor_id=v.created_by_actor_id,
            created_at=v.created_at,
        )
        for v in rows
    ]
    return Page[CaseVersionSummary](items=items, next_cursor=cursor)


@router.get(
    CASE + "/versions/{version}", response_model=CaseVersionOut, **op("cases_version_get", READ, "cases")
)
def cases_version_get(
    case: str,
    version: int,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    c = get_case(db, ctx, case)
    v = get_version(db, c, version)
    if v is None:
        raise HTTPException(404, "Version not found")
    return version_out(db, c, v, mode)


@router.post(CASE + "/restore", response_model=CaseOut, **op("cases_restore", WRITE_CASES, "cases"))
def cases_restore(
    case: str,
    body: CaseRestore,
    response: Response,
    expected: int = Depends(if_match),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Copies an old version's content into a new version."""
    c = get_case(db, ctx, case)
    _check_editable(c, expected)
    old = get_version(db, c, body.version)
    if old is None:
        raise HTTPException(404, "Version not found")
    new = content_of(old, version_tags(db, [old.id])[old.id])
    note = body.change_note or f"Restored version {body.version}"
    _, changes = edit_case(db, ctx, c, expected, new, note)
    if changes:
        changes["restored_from"] = [None, body.version]
        audit.record(db, ctx, "case.restore", "test_case", c.id, changes)
    db.commit()  # a no-op commits too, so an Idempotency-Key replays it
    return current_out(db, c, mode, response)


@router.post(CASE + "/move", response_model=CaseOut, **op("cases_move", WRITE_CASES, "cases"))
def cases_move(
    case: str,
    body: CaseMove,
    response: Response,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Moves the case to another feature of its product; not a content edit, so no new version."""
    c = get_case(db, ctx, case)
    if c.archived_at is not None:
        raise HTTPException(409, "Case is archived")
    product_features(db, ctx, c.product_id, [body.feature_id])
    if body.feature_id != c.feature_id:
        changes = {"feature_id": [c.feature_id, body.feature_id], "entity_version": [c.current_version] * 2}
        c.feature_id = body.feature_id
        audit.record(db, ctx, "case.move", "test_case", c.id, changes)
    db.commit()
    return current_out(db, c, mode, response)


@router.post(CASE + "/archive", response_model=CaseOut, **op("cases_archive", WRITE_CASES, "cases"))
def cases_archive(
    case: str,
    response: Response,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    c = get_case(db, ctx, case)
    if c.archived_at is None:
        c.archived_at = utcnow()
        changes = {"entity_version": [c.current_version] * 2}
        audit.record(db, ctx, "case.archive", "test_case", c.id, changes)
    db.commit()
    return current_out(db, c, mode, response)


@router.post(CASES + "/bulk", response_model=CaseBulkOut, **op("cases_bulk_upsert", WRITE_CASES, "cases"))
def cases_bulk_upsert(
    product: str,
    body: CaseBulkIn,
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """All or nothing: one bad item (422, 409) writes none."""
    p = get_product(db, ctx, product)
    results = []
    for i, item in enumerate(body.items):
        case, v, result = upsert_item(db, ctx, p, item, f"items[{i}]")
        results.append(CaseBulkResult(key=case_key(p, case), id=case.id, version=v.version, result=result))
    db.commit()
    return CaseBulkOut(items=results)


def upsert_item(
    db: Session, ctx: OrgContext, p: Product, item: CaseBulkItem, label: str, action: str = "case.bulk_upsert"
) -> tuple[TestCase, CaseVersion, str]:
    """Create the item's case (no key) or edit it (key + expected_version), with its audit event; nothing
    is committed. Errors start with `label`, so the caller can say which item or row it was."""
    if item.key is None:
        if item.feature_id is None or item.title is None:
            raise HTTPException(422, f"{label}: a new case needs feature_id and title")
        case, v, content = create_case(db, ctx, p, item, item.feature_id, item.title)
        changes = content_changes(None, content)
        changes["entity_version"] = [None, 1]
        result = "created"
    else:
        if item.expected_version is None:
            raise HTTPException(422, f"{label}: updating {item.key} needs expected_version")
        if item.feature_id is not None:
            raise HTTPException(422, f"{label}: use cases_move to change a case's feature")
        m = CASE_KEY.match(item.key)
        case = get_case(db, ctx, item.key) if m and m.group(1) == p.key else None
        if case is None or case.product_id != p.id:
            raise HTTPException(422, f"{label}: {item.key} is not a case of {p.key}")
        _check_editable(case, item.expected_version)
        current = db_current(db, case)
        new = apply_fields(item, content_of(current, version_tags(db, [current.id])[current.id]))
        v, changes = edit_case(db, ctx, case, item.expected_version, new, item.change_note)
        v = v or current
        result = "updated" if changes else "unchanged"
    if changes:
        changes["result"] = [None, result]
        audit.record(db, ctx, action, "test_case", case.id, changes)
    return case, v, result


@router.get(TAGS, response_model=Page[TagOut], **op("tags_list", READ, "cases"))
def tags_list(
    product: str,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Every tag of the product, by name, with how many live cases carry it now."""
    p = get_product(db, ctx, product)
    live = and_(
        TestCase.org_id == CaseVersion.org_id,
        TestCase.id == CaseVersion.case_id,
        TestCase.current_version == CaseVersion.version,
        TestCase.archived_at.is_(None),
    )
    rows = db.execute(
        select(Tag.id, Tag.name, func.count(TestCase.id))
        .select_from(Tag)
        .outerjoin(CaseVersionTag, CaseVersionTag.tag_id == Tag.id)
        .outerjoin(CaseVersion, CaseVersion.id == CaseVersionTag.case_version_id)
        .outerjoin(TestCase, live)
        .where(Tag.org_id == ctx.org.id, Tag.product_id == p.id)
        .group_by(Tag.id, Tag.name)
        .order_by(Tag.name)
    )
    return Page[TagOut](items=[TagOut(id=i, name=n, case_count=c) for i, n, c in rows], next_cursor=None)
