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
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.if_match import if_match
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.v1.cases import (
    CASE,
    CASE_KEY,
    _check_editable,
    case_key,
    content_of,
    current_out,
    db_current,
    get_case,
    subtree,
    upsert_item,
    version_tags,
)
from test_junkie_tcms.api.v1.catalog import get_feature, get_product, require_active_product, rich_mode
from test_junkie_tcms.api.v1.md_bundle import FileError, case_to_md, md_to_row, read_bundle, write_bundle
from test_junkie_tcms.api.v1.report_schemas import ExportIn, ImportIn, ImportOut
from test_junkie_tcms.api.v1.schemas import CaseBulkItem, CaseMarkdownIn, CaseMarkdownOut, CaseOut, Name, RichMode
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
    "description",
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
# The header before cases had a description; its rows keep the stored description on an edit.
LEGACY_COLUMNS = tuple(c for c in COLUMNS if c != "description")
TARGETS = {*COLUMNS, "step_action", "step_expected"}
SEP = " > "
FEATURE_NAME = TypeAdapter(Name)
MAX_IMPORT = 5 * 1024 * 1024
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
    responses={
        200: {
            "content": {"text/csv": {}, "application/zip": {}},
            "description": "The cases as CSV, or as an md-bundle zip of one Markdown file per case",
        }
    },
    **op("exports_create", READ, "cases"),
)
def exports_create(
    product: str,
    body: ExportIn,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The product's cases (or a feature subtree's) at their current version, by case number. `md-bundle`
    is a zip with `<KEY>.md` per case; over MCP it arrives as `{content_type, base64}`. Both import back
    through `imports_create`."""
    p = get_product(db, ctx, product)
    cases = _export_cases(db, ctx, p, body)
    if body.format == "md-bundle":
        broken = [c["key"] for c in cases if "\n" in c["title"] or "\r" in c["title"]]
        if broken:
            raise HTTPException(
                422, f"md-bundle can't hold a title with a line break ({', '.join(broken)}); use csv"
            )
        return Response(
            write_bundle(cases),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{p.key}-cases.zip"'},
        )
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for c in cases:
        writer.writerow(
            [
                *(c[name] for name in COLUMNS[:6]),
                json.dumps(c["steps"], ensure_ascii=False),
                *(c[name] for name in COLUMNS[7:12]),
                json.dumps(c["tags"], ensure_ascii=False),
                json.dumps(c["links"], ensure_ascii=False),
                json.dumps(c["custom"], ensure_ascii=False, sort_keys=True),
            ]
        )
    return Response(out.getvalue(), media_type="text/csv")


def _export_cases(db: Session, ctx: OrgContext, p: Product, body: ExportIn) -> list[dict[str, Any]]:
    """Each case as the export's columns, with `steps`, `tags`, `links` and `custom` as values."""
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
    return [_export_row(p, case, v, tags[v.id], paths) for case, v in rows]


def _export_row(
    p: Product, case: TestCase, v: CaseVersion, tags: list[str], paths: dict[str, str]
) -> dict[str, Any]:
    c = content_of(v, tags)
    return {
        "key": case_key(p, case),
        "version": case.current_version,
        "feature": paths[case.feature_id],
        "title": c["title"],
        "description": doc_to_md(c["description"]),
        "preconditions": doc_to_md(c["preconditions"]),
        "steps": [
            {"id": s["id"], "action": doc_to_md(s["action"]), "expected": doc_to_md(s["expected"])}
            for s in c["steps"]
        ],
        "priority": c["priority"],
        "type": c["type"],
        "status": c["status"],
        "automation": c["automation"],
        "automation_ref": c["automation_ref"] or "",
        "tags": c["tags"],
        "links": c["links"],
        "custom": c["custom"],
    }


## One case as Markdown


@router.get(CASE + "/markdown", response_model=CaseMarkdownOut, **op("cases_markdown_get", READ, "cases"))
def cases_markdown_get(
    case: str,
    response: Response,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The case's current version as one md-bundle file, the same file an `md-bundle` export holds for
    it. The ETag is the version, for `cases_markdown_put`'s `If-Match`."""
    c = get_case(db, ctx, case)
    p = db.get(Product, c.product_id)
    v = db_current(db, c)
    row = _export_row(p, c, v, version_tags(db, [v.id])[v.id], feature_paths(db, ctx.org.id, p.id))
    response.headers["ETag"] = f'"{c.current_version}"'
    return CaseMarkdownOut(case_id=c.id, key=row["key"], version=c.current_version, markdown=case_to_md(row))


@router.put(CASE + "/markdown", response_model=CaseOut, **op("cases_markdown_put", WRITE_CASES, "cases"))
def cases_markdown_put(
    case: str,
    body: CaseMarkdownIn,
    response: Response,
    expected: int = Depends(if_match),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    db: Session = Depends(get_db),
):
    """Save an edited `cases_markdown_get` file as the case's next version, through the same parser and
    write path as an `md-bundle` import. The file's `key` must be this case and its `version` the
    `If-Match` one; a file with no description section keeps the stored description; a changed `feature`
    is 422 (use `cases_move`). An unchanged file writes no version."""
    c = get_case(db, ctx, case)
    p = db.get(Product, c.product_id)
    _check_editable(c, expected)
    try:
        row = md_to_row(body.markdown)
        if row["key"].strip() != case_key(p, c):
            raise RowError("key", f"the file is for {row['key'].strip() or 'no case'}, not {case_key(p, c)}")
        item = _item(db, ctx, p, row, feature_paths(db, ctx.org.id, p.id), create=False)
    except (FileError, RowError) as e:
        raise ProblemError(422, e.detail, errors=[{"row": 1, "column": e.column, "detail": e.detail}]) from e
    item = item.model_copy(update={"change_note": body.change_note})
    _, _, result = upsert_item(db, ctx, p, item, "markdown", action="case.update")
    if result != "unchanged":
        db.commit()
    return current_out(db, c, mode, response)


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


def _feature_path(raw: str) -> str:
    """The row's feature path with each name stripped as `Name` stores it, so `Pay >  Card ` is `Pay > Card`.
    The lookup and `_create_path` both use this one form, so a second import finds what the first created."""
    return SEP.join(name.strip() for name in raw.split(SEP))


def _create_path(db: Session, ctx: OrgContext, p: Product, path: str, paths: dict[str, str]) -> str:
    """Create the missing features of `path` (a `_feature_path`), top down; returns the leaf's id."""
    by_path = {v: k for k, v in reversed(list(paths.items()))}
    parent_id: str | None = None
    names = path.split(SEP)
    for i, name in enumerate(names):
        here = SEP.join(names[: i + 1])
        if here in by_path:
            parent_id = by_path[here]
            continue
        try:
            name = FEATURE_NAME.validate_python(name)
        except ValidationError as e:
            msg = "is empty" if not name else f"is over {e.errors()[0]['ctx']['max_length']} characters"
            raise RowError("feature", f"a feature name in the path {msg}") from e
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
    """The row as a bulk item, after the checks only an import needs (version, feature, path). A column
    the row doesn't have (a mapped CSV that maps nothing to it) is empty on a new case and keeps the
    case's value on an edit."""
    given = set(row)
    row = {c: "" for c in COLUMNS} | row
    key = row["key"].strip() or None
    path = _feature_path(row["feature"])
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
        if "feature" in given and feature_id != case.feature_id:
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
        "description": {"markdown": row["description"]},
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
    if key:
        for column in ("description", "preconditions", "steps", "automation_ref", "tags", "links", "custom"):
            if column not in given:
                del data[column]
    try:
        return CaseBulkItem.model_validate(data)
    except ValidationError as e:
        err = e.errors()[0]
        column = str(err["loc"][0]) if err["loc"] else None
        raise RowError(column, err["msg"]) from e


def apply_mapping(header: list[str], mapping: dict[str, str | None]) -> dict[str, str]:
    """Their column -> ours, for every column the import reads. A 422 lists every bad name: a key not in
    the header, a target that isn't ours, two columns on one target, and a column neither mapped, set to
    null nor already one of ours (so a typo can't drop data)."""

    def refuse(what: str, names) -> None:
        if names:
            raise HTTPException(422, f"{what}: {', '.join(sorted(names))}")

    refuse("The header repeats", {c for c in header if header.count(c) > 1})
    refuse("mapping names columns the csv doesn't have", set(mapping) - set(header))
    refuse("mapping targets that aren't columns", {t for t in mapping.values() if t is not None} - TARGETS)
    refuse(
        "Columns not in the mapping (map them, or map them to null to skip them)",
        {c for c in header if c not in mapping and c not in TARGETS},
    )
    ours = {c: mapping.get(c, c) for c in header if mapping.get(c, c) is not None}
    refuse("More than one column maps to", {t for t in ours.values() if list(ours.values()).count(t) > 1})
    targets = set(ours.values())
    if "title" not in targets:
        raise HTTPException(422, "Nothing maps to title")
    if "steps" in targets and targets & {"step_action", "step_expected"}:
        raise HTTPException(422, "steps can't be used with step_action or step_expected")
    return ours


def _tags(raw: str) -> str:
    """Mapped tags: a JSON list, or else a comma-separated list."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if not isinstance(value, list):
        value = [t.strip() for t in raw.split(",") if t.strip()]
    return json.dumps(value, ensure_ascii=False)


def _csv_rows(text: str, mapping: dict[str, str | None] | None, errors: list) -> list[tuple]:
    """`(n, row in the COLUMNS shape, label, our column -> theirs)` per CSV row. A row with the wrong
    number of columns goes to `errors`."""
    reader = csv.DictReader(io.StringIO(text))
    header = list(reader.fieldnames or ())
    if mapping is None:
        if tuple(header) not in (COLUMNS, LEGACY_COLUMNS):
            raise HTTPException(422, f"The header must be: {','.join(COLUMNS)}")
        ours = {c: c for c in header}
    else:
        ours = apply_mapping(header, mapping)
    theirs = {t: c for c, t in ours.items()}
    if "steps" not in theirs:
        theirs["steps"] = theirs.get("step_action") or theirs.get("step_expected")

    def column_of(column: str | None) -> str | None:
        return theirs.get(column, column) if column else column

    out = []
    for n, raw in enumerate(reader, start=1):
        if None in raw or any(v is None for v in raw.values()):
            errors.append({"row": n, "column": None, "detail": f"must have {len(header)} columns"})
            continue
        if mapping is None:
            out.append((n, raw, "", column_of))
            continue
        row = {c: raw[theirs[c]] for c in COLUMNS if theirs.get(c)}
        if "step_action" in theirs or "step_expected" in theirs:
            action = raw[theirs["step_action"]] if "step_action" in theirs else ""
            expected = raw[theirs["step_expected"]] if "step_expected" in theirs else ""
            step = [{"action": action, "expected": expected}] if action.strip() or expected.strip() else []
            row["steps"] = json.dumps(step, ensure_ascii=False)
        if row.get("tags", "").strip():
            row["tags"] = _tags(row["tags"])
        out.append((n, row, "", column_of))
    return out


def _bundle_rows(files: list[tuple[str, bytes]], errors: list) -> list[tuple]:
    """`(n, row, label, column_of)` per `.md` file, by name; a file that doesn't parse goes to `errors`."""
    out = []
    for n, (name, data) in enumerate(files, start=1):
        try:
            row = md_to_row(data.decode("utf-8"))
        except UnicodeDecodeError:
            errors.append({"row": n, "column": None, "detail": f"{name}: not UTF-8"})
            continue
        except FileError as e:
            errors.append({"row": n, "column": e.column, "detail": f"{name}: {e.detail}"})
            continue
        out.append((n, row, f"{name}: ", lambda c: c))
    return out


@router.post(PRODUCT + "/imports", response_model=ImportOut, **op("imports_create", WRITE_CASES, "cases"))
def imports_create(
    product: str,
    body: ImportIn,
    ctx: OrgContext = Depends(require_scope(WRITE_CASES)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Import a CSV in the export's format, a CSV with other column names through `mapping`, or an
    `md-bundle` zip (base64 in `bundle`). A row with `key` edits that case and must carry the `version`
    it was exported at; a row without one creates a case in `feature`. All or nothing: any bad row gives
    422 with `errors: [{row, column, detail}]` (row 1 is the first after the header, or the first `.md`
    file by name) and writes nothing. `dry_run` checks every row and returns the counts without writing;
    that answer is not kept for an `Idempotency-Key` replay."""
    if body.format == "csv":
        if body.csv is None or body.bundle is not None:
            raise HTTPException(422, "format csv takes `csv`, not `bundle`")
        if len(body.csv.encode()) > MAX_IMPORT:
            raise HTTPException(413, "csv is over 5 MB")
    else:
        if body.bundle is None or body.csv is not None:
            raise HTTPException(422, "format md-bundle takes `bundle`, not `csv`")
        if body.mapping is not None:
            raise HTTPException(422, "mapping is for csv only")
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    errors: list[dict[str, Any]] = []
    if body.format == "csv":
        source = _csv_rows(body.csv, body.mapping, errors)
    else:
        source = _bundle_rows(read_bundle(body.bundle, MAX_IMPORT), errors)
    paths = feature_paths(db, ctx.org.id, p.id)
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    keys: list[str] = []
    seen: set[str] = set()
    for n, row, label, column_of in source:
        key = row.get("key", "").strip()
        if key and key in seen:
            errors.append({"row": n, "column": column_of("key"), "detail": label + f"{key} appears twice"})
            continue
        seen.add(key)
        try:
            item = _item(db, ctx, p, row, paths, body.create_features)
            case, _, result = upsert_item(db, ctx, p, item, f"row {n}", action="case.import")
        except RowError as e:
            errors.append({"row": n, "column": column_of(e.column), "detail": label + e.detail})
            continue
        except HTTPException as e:
            errors.append({"row": n, "column": None, "detail": label + str(e.detail)})
            continue
        counts[result] += 1
        keys.append(case_key(p, case))
    if errors:
        db.rollback()
        raise ProblemError(422, f"{len(errors)} row(s) can't be imported; nothing was written", errors=errors)
    if not keys:
        db.rollback()
        raise HTTPException(422, f"The {'csv' if body.format == 'csv' else 'bundle'} has no rows")
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
