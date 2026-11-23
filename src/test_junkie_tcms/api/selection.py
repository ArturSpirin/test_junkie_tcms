"""Which cases a plan, features, a list of ids or a whole product select. `plans_resolve`, the plan entry
counts and the cycle routes (T4) share it, so a plan resolves to the same cases wherever it is read.

The `*_candidates` functions and `entry_cases` return every selected case, live or not; `split` keeps the
live ones (not archived, not `deprecated`) and counts what it left out, for `cycles_preview`.
`plan_cases` returns live cases only.
"""

from dataclasses import dataclass, field

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from test_junkie_tcms.db.models import (
    CaseVersion,
    CaseVersionTag,
    Feature,
    PlanEntry,
    Tag,
    TestCase,
    TestPlan,
)


def plan_entries(db: Session, plan: TestPlan) -> list[PlanEntry]:
    rows = db.scalars(select(PlanEntry).where(PlanEntry.org_id == plan.org_id, PlanEntry.plan_id == plan.id))
    return sorted(rows, key=lambda e: (e.position, e.id))


def feature_children(db: Session, org_id: str, product_id: str) -> dict[str | None, list[str]]:
    """The product's feature ids per parent id (None for the top level)."""
    children: dict[str | None, list[str]] = {}
    for f_id, parent in db.execute(
        select(Feature.id, Feature.parent_id).where(
            Feature.org_id == org_id, Feature.product_id == product_id
        )
    ):
        children.setdefault(parent, []).append(f_id)
    return children


def descendants(children: dict[str | None, list[str]], feature_ids: list[str]) -> set[str]:
    """The features and every feature under them."""
    seen: set[str] = set()
    todo = list(feature_ids)
    while todo:
        f_id = todo.pop()
        if f_id not in seen:
            seen.add(f_id)
            todo.extend(children.get(f_id, []))
    return seen


@dataclass
class ProductIndex:
    """A product's cases and feature tree, read once, so resolving many entries (or every plan of a list)
    runs a fixed number of queries. The current versions' fields and tags load on the first query entry."""

    db: Session
    org_id: str
    product_id: str
    cases: list[TestCase] = field(default_factory=list)
    by_feature: dict[str, list[TestCase]] = field(default_factory=dict)
    children: dict[str | None, list[str]] = field(default_factory=dict)
    _current: dict[str, tuple[str, str, str, set[str]]] | None = None

    @classmethod
    def load(cls, db: Session, org_id: str, product_id: str) -> "ProductIndex":
        index = cls(db, org_id, product_id, product_cases(db, org_id, product_id))
        for c in index.cases:
            index.by_feature.setdefault(c.feature_id, []).append(c)
        index.children = feature_children(db, org_id, product_id)
        return index

    def subtree(self, feature_ids: list[str]) -> set[str]:
        return descendants(self.children, feature_ids)

    def current(self) -> dict[str, tuple[str, str, str, set[str]]]:
        """Per case id: its current version's priority, type, automation and tag names."""
        if self._current is None:
            on_current = and_(
                CaseVersion.org_id == TestCase.org_id,
                CaseVersion.case_id == TestCase.id,
                CaseVersion.version == TestCase.current_version,
            )
            where = (TestCase.org_id == self.org_id, TestCase.product_id == self.product_id)
            rows = self.db.execute(
                select(TestCase.id, CaseVersion.priority, CaseVersion.type, CaseVersion.automation)
                .join(CaseVersion, on_current)
                .where(*where)
            )
            self._current = {case_id: (pr, ty, au, set()) for case_id, pr, ty, au in rows}
            for case_id, name in self.db.execute(
                select(TestCase.id, Tag.name)
                .join(CaseVersion, on_current)
                .join(CaseVersionTag, CaseVersionTag.case_version_id == CaseVersion.id)
                .join(Tag, Tag.id == CaseVersionTag.tag_id)
                .where(*where)
            ):
                self._current[case_id][3].add(name)
        return self._current


def matches(fields: tuple[str, str, str, set[str]], q: dict) -> bool:
    """A current version matches a query: any of `tags`, and each non-empty field list."""
    priority, type_, automation, tags = fields
    for wanted, value in (
        (q.get("priority"), priority),
        (q.get("type"), type_),
        (q.get("automation"), automation),
    ):
        if wanted and value not in wanted:
            return False
    return not q.get("tags") or bool(tags & {t.lower() for t in q["tags"]})


def entry_cases(index: ProductIndex, entry: PlanEntry) -> list[TestCase]:
    """The cases one entry selects, live or not, by number: its case, its feature subtree's cases, or the
    cases whose current version matches its query."""
    if entry.case_id is not None:
        return [c for c in index.cases if c.id == entry.case_id]
    if entry.feature_id is not None:
        features = index.subtree([entry.feature_id])
        return sorted((c for f in features for c in index.by_feature.get(f, [])), key=lambda c: c.number)
    current = index.current()
    return [c for c in index.cases if c.id in current and matches(current[c.id], entry.query or {})]


def is_live(c: TestCase) -> bool:
    return c.archived_at is None and c.status != "deprecated"


def split(found: list[TestCase]) -> tuple[list[TestCase], dict[str, int]]:
    """Each case once (first wins), live ones in order, and the counts of those left out."""
    seen: dict[str, TestCase] = {}
    for c in found:
        seen.setdefault(c.id, c)
    skipped = {"archived": 0, "deprecated": 0}
    live = []
    for c in seen.values():
        if c.archived_at is not None:
            skipped["archived"] += 1
        elif c.status == "deprecated":
            skipped["deprecated"] += 1
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


def plan_candidates(db: Session, plan: TestPlan, index: ProductIndex | None = None) -> list[TestCase]:
    """The plan's cases in entry order, before `split`."""
    index = index or ProductIndex.load(db, plan.org_id, plan.product_id)
    return [c for e in plan_entries(db, plan) for c in entry_cases(index, e)]


def plan_cases(db: Session, plan: TestPlan) -> list[TestCase]:
    """The plan's live cases in entry order, each once (its first entry wins)."""
    return split(plan_candidates(db, plan))[0]


def entry_counts(entries: list[PlanEntry], index: ProductIndex) -> dict[str, tuple[int, int]]:
    """Per entry id: how many live cases it selects, and how many of those no earlier entry did. The second
    counts sum to the `plan_cases` total."""
    seen: set[str] = set()
    out: dict[str, tuple[int, int]] = {}
    for e in entries:
        live = [c.id for c in entry_cases(index, e) if is_live(c)]
        new = [i for i in dict.fromkeys(live) if i not in seen]
        seen.update(new)
        out[e.id] = (len(set(live)), len(new))
    return out


def feature_candidates(db: Session, org_id: str, product_id: str, feature_ids: list[str]) -> list[TestCase]:
    """The cases under the features and their sub-features, by number, before `split`."""
    index = ProductIndex.load(db, org_id, product_id)
    features = index.subtree(feature_ids)
    return [c for c in index.cases if c.feature_id in features]
