"""Which cases a plan, features, a list of ids or a whole product select. `plans_resolve` and the
cycle routes (T4) share it, so a plan resolves to the same cases wherever it is read.

Every function returns live cases only (not archived, not `deprecated`); `split` also counts what it
left out, for `cycles_preview`.
"""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from test_junkie_tcms.api.v1.cases import subtree
from test_junkie_tcms.db.models import CaseVersion, CaseVersionTag, PlanEntry, Tag, TestCase, TestPlan


def plan_entries(db: Session, plan: TestPlan) -> list[PlanEntry]:
    rows = db.scalars(select(PlanEntry).where(PlanEntry.org_id == plan.org_id, PlanEntry.plan_id == plan.id))
    return sorted(rows, key=lambda e: (e.position, e.id))


def query_cases(db: Session, org_id: str, product_id: str, q: dict) -> list[TestCase]:
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


def is_live(c: TestCase) -> bool:
    return c.archived_at is None and c.status != "deprecated"


def split(found: list[TestCase], skip_drafts: bool = False) -> tuple[list[TestCase], dict[str, int]]:
    """Each case once (first wins), live ones in order, and the counts of those left out. With
    `skip_drafts`, draft cases are left out too, under `skipped["draft"]`."""
    seen: dict[str, TestCase] = {}
    for c in found:
        seen.setdefault(c.id, c)
    skipped = {"archived": 0, "deprecated": 0}
    if skip_drafts:
        skipped["draft"] = 0
    live = []
    for c in seen.values():
        if c.archived_at is not None:
            skipped["archived"] += 1
        elif c.status == "deprecated":
            skipped["deprecated"] += 1
        elif skip_drafts and c.status == "draft":
            skipped["draft"] += 1
        else:
            live.append(c)
    return live, skipped


def product_cases(db: Session, org_id: str, product_id: str) -> list[TestCase]:
    """Every case of the product, live or not, by number."""
    return list(
        db.scalars(
            select(TestCase)
            .where(TestCase.org_id == org_id, TestCase.product_id == product_id)
            .order_by(TestCase.number)
        )
    )


def plan_candidates(db: Session, plan: TestPlan) -> list[TestCase]:
    """The plan's cases in entry order, before `split`."""
    cases = {c.id: c for c in product_cases(db, plan.org_id, plan.product_id)}
    by_feature: dict[str, list[TestCase]] = {}
    for c in cases.values():
        by_feature.setdefault(c.feature_id, []).append(c)
    found: list[TestCase] = []
    for e in plan_entries(db, plan):
        if e.case_id is not None:
            found += [cases[e.case_id]] if e.case_id in cases else []
        elif e.feature_id is not None:
            features = subtree(db, plan.org_id, plan.product_id, [e.feature_id])
            found += sorted((c for f in features for c in by_feature.get(f, [])), key=lambda c: c.number)
        else:
            found += query_cases(db, plan.org_id, plan.product_id, e.query or {})
    return found


def plan_cases(db: Session, plan: TestPlan) -> list[TestCase]:
    """The plan's live cases in entry order, each once (its first entry wins)."""
    return split(plan_candidates(db, plan))[0]


def feature_candidates(db: Session, org_id: str, product_id: str, feature_ids: list[str]) -> list[TestCase]:
    """The cases under the features and their sub-features, by number, before `split`."""
    features = subtree(db, org_id, product_id, feature_ids)
    return [c for c in product_cases(db, org_id, product_id) if c.feature_id in features]
