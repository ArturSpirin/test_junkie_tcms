"""Reports (T6): where a release stands, per org, product, feature and cycle.

A case's release status is its newest result in any cycle of the release, on the case's current
version. A result on an older version doesn't count: the case is `untested` and `stale`, so a release
can't look `ready` on case text that changed after the run. Live cases of the release's features that
are in no cycle are `untested` and `not_in_cycle`. Archived cases are left out.
"""

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params
from test_junkie_tcms.api.selection import feature_candidates, is_live
from test_junkie_tcms.api.v1.cases import case_key, subtree
from test_junkie_tcms.api.v1.catalog import get_feature, get_product, get_release
from test_junkie_tcms.api.v1.cycles import counts as cycle_counts
from test_junkie_tcms.api.v1.cycles import get_cycle
from test_junkie_tcms.api.v1.report_schemas import (
    CycleReport,
    FeatureCaseStatus,
    FeatureCounts,
    FeatureReport,
    OrgReport,
    ProductReport,
    ReleaseReport,
    ReleaseTotals,
    ReportCounts,
    ReportRelease,
)
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ
from test_junkie_tcms.db.models import (
    RELEASE_STATUSES,
    CaseVersion,
    Cycle,
    CycleCase,
    Feature,
    Product,
    Release,
    ReleaseFeature,
    TestCase,
)

router = APIRouter(tags=["reports"])

LISTED = ("planned", "in_progress", "released")  # a product report leaves out `cancelled` releases


@dataclass
class CaseStatus:
    case: TestCase
    status: str = "untested"
    stale: bool = False
    not_in_cycle: bool = False
    cycle_id: str | None = None
    last_result_at: datetime | None = None


def release_feature_ids(db: Session, org_id: str, release: Release) -> list[str]:
    return list(
        db.scalars(
            select(ReleaseFeature.feature_id).where(
                ReleaseFeature.org_id == org_id, ReleaseFeature.release_id == release.id
            )
        )
    )


def release_status(db: Session, org_id: str, release: Release) -> dict[str, CaseStatus]:
    """Each case's status in the release, by case id."""
    rows = db.execute(
        select(CycleCase, TestCase)
        .join(Cycle, and_(Cycle.org_id == CycleCase.org_id, Cycle.id == CycleCase.cycle_id))
        .join(TestCase, and_(TestCase.org_id == CycleCase.org_id, TestCase.id == CycleCase.case_id))
        .where(CycleCase.org_id == org_id, Cycle.release_id == release.id, TestCase.archived_at.is_(None))
        # NULLS LAST on both databases: a row with no run never overrides a result.
        .order_by(CycleCase.last_result_at.desc().nullslast(), CycleCase.id.desc())
    )
    out: dict[str, CaseStatus] = {}
    decided: set[str] = set()
    for cc, case in rows:
        s = out.setdefault(case.id, CaseStatus(case, cycle_id=cc.cycle_id))
        if case.id in decided or cc.status == "untested":
            continue
        if cc.case_version != case.current_version:
            s.stale = True
            continue
        s.status, s.stale, s.cycle_id, s.last_result_at = cc.status, False, cc.cycle_id, cc.last_result_at
        decided.add(case.id)
    feature_ids = release_feature_ids(db, org_id, release)
    if feature_ids:
        for case in feature_candidates(db, org_id, release.product_id, feature_ids):
            if is_live(case) and case.id not in out:
                out[case.id] = CaseStatus(case, not_in_cycle=True)
    return out


def tally(statuses: list[CaseStatus]) -> ReportCounts:
    c = ReportCounts()
    for s in statuses:
        setattr(c, s.status, getattr(c, s.status) + 1)
        c.total += 1
        c.not_in_cycle += s.not_in_cycle
        c.stale += s.stale
    return c


def is_ready(c: ReportCounts) -> bool:
    return c.total > 0 and c.fail + c.error + c.untested == 0


def release_out(r: Release) -> ReportRelease:
    return ReportRelease(id=r.id, version=r.version, name=r.name, status=r.status, product_id=r.product_id)


@dataclass
class ReleaseRows:
    counts: ReportCounts
    ready: bool
    features: list[FeatureCounts]


def release_rows(db: Session, org_id: str, release: Release) -> ReleaseRows:
    """The release's totals, `ready`, and one row per feature: the one source for every report's `ready`.

    Rows start from the release's features, so a release feature with no case has a row (`total: 0`).
    A case counts once, in the row of its nearest release feature at or above its own feature; a case
    under no release feature (pulled in by a cycle of the release) counts in its own feature's row,
    with `in_release: false`. A row's `ready` looks at every case under the feature, so a release
    feature whose cases all sit in a listed sub-feature's row is covered. The release is `ready` when
    its totals are and every release feature has at least one case under it. A release feature that
    has since been archived is retired: it needs no case, and gets a row only when a case counts in it.
    """
    statuses = list(release_status(db, org_id, release).values())
    wanted = set(release_feature_ids(db, org_id, release))
    features = {
        f.id: f
        for f in db.scalars(
            select(Feature).where(Feature.org_id == org_id, Feature.product_id == release.product_id)
        )
    }

    def chain(f_id: str | None) -> list[str]:
        """The feature and every feature above it, nearest first."""
        out: list[str] = []
        while f_id is not None and f_id not in out:
            out.append(f_id)
            f = features.get(f_id)
            f_id = f.parent_id if f else None
        return out

    required = [f_id for f_id in wanted if f_id in features and features[f_id].archived_at is None]
    rows: dict[str, list[CaseStatus]] = {f_id: [] for f_id in required}
    under: dict[str, list[CaseStatus]] = {f_id: [] for f_id in wanted}
    for s in statuses:
        above = [f_id for f_id in chain(s.case.feature_id) if f_id in wanted]
        rows.setdefault(above[0] if above else s.case.feature_id, []).append(s)
        for f_id in above:
            under[f_id].append(s)

    def row(f_id: str, cases: list[CaseStatus]) -> FeatureCounts:
        f = features.get(f_id)
        listed = f_id in wanted
        return FeatureCounts(
            feature_id=f_id,
            name=f.name if f else "",
            in_release=listed,
            counts=tally(cases),
            ready=is_ready(tally(under[f_id] if listed else cases)),
        )

    out = sorted(
        (row(f_id, cases) for f_id, cases in rows.items()),
        key=lambda r: (not r.in_release, r.name, r.feature_id),
    )
    c = tally(statuses)
    return ReleaseRows(counts=c, ready=is_ready(c) and all(under[f_id] for f_id in required), features=out)


def release_totals(db: Session, org_id: str, r: Release) -> ReleaseTotals:
    rr = release_rows(db, org_id, r)
    return ReleaseTotals(release=release_out(r), counts=rr.counts, ready=rr.ready)


def product_releases(db: Session, org_id: str, product_id: str, statuses: tuple[str, ...]) -> list[Release]:
    return list(
        db.scalars(
            select(Release)
            .where(Release.org_id == org_id, Release.product_id == product_id, Release.status.in_(statuses))
            .order_by(Release.created_at, Release.id)
        )
    )


@router.get(
    "/orgs/{org}/releases/{release_id}/report",
    response_model=ReleaseReport,
    **op("reports_release", READ, "reports"),
)
def reports_release(
    release_id: str,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Release readiness: the counts, `ready`, one row per release feature (`in_release: true`, even with
    no cases), then rows for cases of features outside the release (`in_release: false`). Not ready while
    a release feature has no case."""
    r = get_release(db, ctx, release_id)
    rr = release_rows(db, ctx.org.id, r)
    return ReleaseReport(release=release_out(r), counts=rr.counts, ready=rr.ready, features=rr.features)


@router.get(
    "/orgs/{org}/products/{product}/report",
    response_model=ProductReport,
    **op("reports_product", READ, "reports"),
)
def reports_product(
    product: str,
    release: str | None = Query(None, description="A release id; default every release that isn't cancelled"),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    if release is not None:
        r = get_release(db, ctx, release)
        if r.product_id != p.id:
            raise HTTPException(422, f"Release {release} is not a release of {p.key}")
        releases = [r]
    else:
        releases = product_releases(db, ctx.org.id, p.id, LISTED)
    return ProductReport(
        product_id=p.id, product_key=p.key, releases=[release_totals(db, ctx.org.id, r) for r in releases]
    )


@router.get("/orgs/{org}/report", response_model=OrgReport, **op("reports_org", READ, "reports"))
def reports_org(
    release_status_: list[str] = Query(
        [], alias="release_status", description="Repeatable; default planned and in_progress"
    ),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Every product the caller can see (not archived), with its releases in the given statuses."""
    wanted = tuple(release_status_) or ("planned", "in_progress")
    bad = [s for s in wanted if s not in RELEASE_STATUSES]
    if bad:
        raise HTTPException(422, f"Unknown release_status: {', '.join(bad)}")
    query = select(Product).where(Product.org_id == ctx.org.id, Product.archived_at.is_(None))
    if ctx.product_ids is not None:
        query = query.where(Product.id.in_(ctx.product_ids))
    products = []
    for p in db.scalars(query.order_by(Product.key)):
        releases = product_releases(db, ctx.org.id, p.id, wanted)
        products.append(
            ProductReport(
                product_id=p.id,
                product_key=p.key,
                releases=[release_totals(db, ctx.org.id, r) for r in releases],
            )
        )
    return OrgReport(products=products)


@router.get(
    "/orgs/{org}/features/{feature_id}/report",
    response_model=FeatureReport,
    **op("reports_feature", READ, "reports"),
)
def reports_feature(
    feature_id: str,
    release: str = Query(..., description="A release id of the feature's product"),
    params: PageParams = Depends(page_params),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The feature subtree's cases in the release: totals, and one page of cases by case number."""
    f = get_feature(db, ctx, feature_id)
    r = get_release(db, ctx, release)
    if r.product_id != f.product_id:
        raise HTTPException(422, f"Release {release} is not a release of the feature's product")
    tree = subtree(db, ctx.org.id, f.product_id, [f.id])
    statuses = sorted(
        (s for s in release_status(db, ctx.org.id, r).values() if s.case.feature_id in tree),
        key=lambda s: s.case.number,
    )
    after = int(params.cursor) if params.cursor and params.cursor.isdigit() else 0
    rest = [s for s in statuses if s.case.number > after]
    page = rest[: params.limit]
    cursor = str(page[-1].case.number) if len(rest) > params.limit else None
    p = db.get(Product, f.product_id)
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
            .where(TestCase.id.in_([s.case.id for s in page]))
        ).all()
    )
    items = [
        FeatureCaseStatus(
            id=s.case.id,
            key=case_key(p, s.case),
            title=titles.get(s.case.id, ""),
            feature_id=s.case.feature_id,
            status=s.status,
            stale=s.stale,
            cycle_id=s.cycle_id,
            last_result_at=s.last_result_at,
        )
        for s in page
    ]
    return FeatureReport(
        feature_id=f.id, release=release_out(r), counts=tally(statuses), items=items, next_cursor=cursor
    )


@router.get(
    "/orgs/{org}/cycles/{cycle_id}/report", response_model=CycleReport, **op("reports_cycle", READ, "reports")
)
def reports_cycle(
    cycle_id: str,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """One cycle's counts by status, as they stand (pinned versions, no stale check)."""
    cy = get_cycle(db, ctx, cycle_id)
    c = cycle_counts(db, [cy.id])[cy.id]
    return CycleReport(cycle_id=cy.id, counts=c, total=sum(c.values()))
