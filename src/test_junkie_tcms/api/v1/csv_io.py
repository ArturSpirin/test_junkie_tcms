"""CSV export and import of cases (T6).

The export's columns are the import's: a file exported from one product imports into another (new
cases), or back into the same one (edits, checked against `version`). Rich fields travel as Markdown;
`steps`, `tags`, `links` and `custom` are JSON; `feature` is the feature path, names joined by " > ".

Import is synchronous and all or nothing: any bad row is a 422 with every row error, and nothing is
written. Edits go through the same `upsert_item` as `cases_bulk_upsert`, so each case gets its own
`case.import` audit event, plus one `cases.import` summary on the product.
"""

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.v1.cases import CASE_KEY, case_key, content_of, subtree, upsert_item, version_tags
from test_junkie_tcms.api.v1.catalog import get_feature, get_product, require_active_product
from test_junkie_tcms.api.v1.report_schemas import ExportIn, ImportIn, ImportOut
from test_junkie_tcms.api.v1.schemas import CaseBulkItem
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_CASES
from test_junkie_tcms.db.models import CaseVersion, Feature, Product, TestCase
from test_junkie_tcms.errors import ProblemError
from test_junkie_tcms.richtext import doc_to_md, empty_doc

router = APIRouter(tags=["cases"])

PRODUCT = "/orgs/{org}/products/{product}"
COLUMNS = (
    "key",
    "version",
    "feature",
    "title",
    "preconditions",
    "steps",
    "priority",
    "type",
    "status",
    "automation",
    "automation_ref",
    "tags",
    "links",
    "custom",
)
SEP = " > "
MAX_CSV = 5 * 1024 * 1024
JSON_COLUMNS = {"steps": list, "tags": list, "links": list, "custom": dict}


def feature_paths(db: Session, org_id: str, product_id: str) -> dict[str, str]:
    """Feature id -> path. Sibling names aren't unique; the first by (position, id) wins on import."""
    rows = list(
        db.execute(
            select(Feature.id, Feature.parent_id, Feature.name)
            .where(Feature.org_id == org_id, Feature.product_id == product_id)
            .order_by(Feature.position, Feature.id)
        )
    )
    parent = {f_id: (p_id, name) for f_id, p_id, name in rows}
    out: dict[str, str] = {}

    def path(f_id: str) -> str:
        if f_id not in out:
            p_id, name = parent[f_id]
            out[f_id] = name if p_id is None else path(p_id) + SEP + name
        return out[f_id]

    for f_id, _, _ in rows:
        path(f_id)
    return out


## Export


@router.post(
    PRODUCT + "/exports",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "The cases as CSV"}},
    **op("exports_create", READ, "cases"),
)
def exports_create(
    product: str,
    body: ExportIn,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The product's cases (or a feature subtree's) at their current version, by case number."""
    p = get_product(db, ctx, product)
    if body.format != "csv":
        raise HTTPException(422, "md-bundle export is not supported yet")
    query = (
        select(TestCase, CaseVersion)
        .join(
            CaseVersion,
            (CaseVersion.org_id == TestCase.org_id)
            & (CaseVersion.case_id == TestCase.id)
            & (CaseVersion.version == TestCase.current_version),
        )
        .where(TestCase.org_id == ctx.org.id, TestCase.product_id == p.id)
    )
    if body.feature is not None:
        f = get_feature(db, ctx, body.feature)
        if f.product_id != p.id:
            raise HTTPException(422, f"Feature {body.feature} is not a feature of {p.key}")
        query = query.where(TestCase.feature_id.in_(subtree(db, ctx.org.id, p.id, [f.id])))
    if not body.include_archived:
        query = query.where(TestCase.archived_at.is_(None))
    rows = list(db.execute(query.order_by(TestCase.number)))
    tags = version_tags(db, [v.id for _, v in rows])
    paths = feature_paths(db, ctx.org.id, p.id)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for case, v in rows:
        c = content_of(v, tags[v.id])
        steps = [
            {"id": s["id"], "action": doc_to_md(s["action"]), "expected": doc_to_md(s["expected"])}
            for s in c["steps"]
        ]
        writer.writerow(
            [
                case_key(p, case),
                case.current_version,
                paths[case.feature_id],
                c["title"],
                doc_to_md(c["preconditions"]),
                json.dumps(steps, ensure_ascii=False),
                c["priority"],
                c["type"],
                c["status"],
                c["automation"],
                c["automation_ref"] or "",
                json.dumps(c["tags"], ensure_ascii=False),
                json.dumps(c["links"], ensure_ascii=False),
                json.dumps(c["custom"], ensure_ascii=False, sort_keys=True),
            ]
        )
    return Response(out.getvalue(), media_type="text/csv")


## Import


class RowError(Exception):
    def __init__(self, column: str | None, detail: str):
        self.column, self.detail = column, detail


def _json(row: dict[str, str], column: str) -> Any:
    raw = row[column].strip()
    if not raw:
        return JSON_COLUMNS[column]()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RowError(column, f"not JSON: {e.msg}") from e
    if not isinstance(value, JSON_COLUMNS[column]):
        raise RowError(column, f"must be a JSON {'object' if column == 'custom' else 'list'}")
    return value


def _create_path(db: Session, ctx: OrgContext, p: Product, path: str, paths: dict[str, str]) -> str:
    """Create the missing features of `path`, top down; returns the leaf's id."""
    by_path = {v: k for k, v in reversed(list(paths.items()))}
    parent_id: str | None = None
    names = path.split(SEP)
    for i, name in enumerate(names):
        here = SEP.join(names[: i + 1])
        if here in by_path:
            parent_id = by_path[here]
            continue
        if not name.strip():
            raise RowError("feature", "a feature name in the path is empty")
        siblings = db.scalar(
            select(func.count())
            .select_from(Feature)
            .where(Feature.org_id == ctx.org.id, Feature.product_id == p.id, Feature.parent_id == parent_id)
        )
        f = Feature(
            org_id=ctx.org.id,
            product_id=p.id,
            parent_id=parent_id,
            name=name,
            description=empty_doc(),
            description_text="",
            owner_actor_id=None,
            position=siblings,
        )
        db.add(f)
        db.flush()
        audit.record(
            db,
            ctx,
            "feature.create",
            "feature",
            f.id,
            {
                "name": [None, name],
                "parent_id": [None, parent_id],
                "description": [None, ""],
                "owner_actor_id": [None, None],
            },
        )
        paths[f.id] = here
        by_path[here] = f.id
        parent_id = f.id
    return parent_id


def _item(
    db: Session, ctx: OrgContext, p: Product, row: dict[str, str], paths: dict[str, str], create: bool
) -> CaseBulkItem:
    """The row as a bulk item, after the checks only an import needs (version, feature, path)."""
    key = row["key"].strip() or None
    path = row["feature"].strip()
    by_path = {v: k for k, v in reversed(list(paths.items()))}
    feature_id = by_path.get(path)
    if key is not None:
        m = CASE_KEY.match(key)
        case = None
        if m and m.group(1) == p.key:
            case = db.scalar(
                select(TestCase).where(
                    TestCase.org_id == ctx.org.id,
                    TestCase.product_id == p.id,
                    TestCase.number == int(m.group(2)),
                )
            )
        if case is None:
            raise RowError("key", f"{key} is not a case of {p.key}")
        version = row["version"].strip()
        if not version.isdigit():
            raise RowError("version", "a row with a key needs the case version it was exported at")
        if int(version) != case.current_version:
            raise RowError(
                "version", f"{key} is at version {case.current_version}, not {version}; export it again"
            )
        if feature_id != case.feature_id:
            raise RowError("feature", f"{key} is in another feature; use cases_move to move it")
        feature_id = None
    elif feature_id is None:
        if not path:
            raise RowError("feature", "a new case needs a feature")
        if not create:
            raise RowError("feature", f"no feature {path!r}; pass create_features to create it")
        feature_id = _create_path(db, ctx, p, path, paths)
    steps = _json(row, "steps")
    for s in steps:
        if not isinstance(s, dict):
            raise RowError("steps", "each step must be a JSON object")
    data: dict[str, Any] = {
        "key": key,
        "expected_version": int(row["version"]) if key else None,
        "feature_id": feature_id,
        "title": row["title"] or None,
        "preconditions": {"markdown": row["preconditions"]},
        "steps": [
            {
                **({"id": s["id"]} if key and s.get("id") else {}),
                "action": {"markdown": s.get("action") or ""},
                "expected": {"markdown": s.get("expected") or ""},
            }
            for s in steps
        ],
        "automation_ref": row["automation_ref"] or None,
        "tags": _json(row, "tags"),
        "links": _json(row, "links"),
        "custom": _json(row, "custom"),
    }
    for column in ("priority", "type", "status", "automation"):
        if row[column].strip():
            data[column] = row[column].strip()
    try:
        return CaseBulkItem.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        column = str(err["loc"][0]) if err["loc"] else None
        raise RowError(column, err["msg"]) from e


@router.post(PRODUCT + "/imports", response_model=ImportOut, **op("imports_create", WRITE_CASES, "cases"))
def imports_create(
    product: str,
    body: ImportIn,
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Import a CSV in the export's format. A row with `key` edits that case and must carry the
    `version` it was exported at; a row without one creates a case in `feature`. All or nothing: any
    bad row gives 422 with `errors: [{row, column, detail}]` (row 1 is the first after the header) and
    writes nothing. `dry_run` checks every row and returns the counts without writing; that answer is
    not kept for an `Idempotency-Key` replay."""
    if body.mapping is not None:
        raise HTTPException(422, "mapping is not supported yet; use the export's columns")
    if len(body.csv.encode()) > MAX_CSV:
        raise HTTPException(413, "csv is over 5 MB")
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    reader = csv.DictReader(io.StringIO(body.csv))
    if tuple(reader.fieldnames or ()) != COLUMNS:
        raise HTTPException(422, f"The header must be: {','.join(COLUMNS)}")
    paths = feature_paths(db, ctx.org.id, p.id)
    errors: list[dict[str, Any]] = []
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    keys: list[str] = []
    seen: set[str] = set()
    for n, row in enumerate(reader, start=1):
        if None in row or any(v is None for v in row.values()):
            errors.append({"row": n, "column": None, "detail": f"must have {len(COLUMNS)} columns"})
            continue
        key = row["key"].strip()
        if key and key in seen:
            errors.append({"row": n, "column": "key", "detail": f"{key} appears twice"})
            continue
        seen.add(key)
        try:
            item = _item(db, ctx, p, row, paths, body.create_features)
            case, _, result = upsert_item(db, ctx, p, item, f"row {n}", action="case.import")
        except RowError as e:
            errors.append({"row": n, "column": e.column, "detail": e.detail})
            continue
        except HTTPException as e:
            errors.append({"row": n, "column": None, "detail": str(e.detail)})
            continue
        counts[result] += 1
        keys.append(case_key(p, case))
    if errors:
        db.rollback()
        raise ProblemError(422, f"{len(errors)} row(s) can't be imported; nothing was written", errors=errors)
    if not keys:
        db.rollback()
        raise HTTPException(422, "The csv has no rows")
    if body.dry_run:
        db.rollback()
        return ImportOut(**counts, keys=keys, dry_run=True)
    audit.record(
        db,
        ctx,
        "cases.import",
        "product",
        p.id,
        {k: [None, v] for k, v in counts.items()} | {"rows": [None, len(keys)]},
    )
    db.commit()
    return ImportOut(**counts, keys=keys, dry_run=False)
