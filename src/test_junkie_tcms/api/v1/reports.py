"""Reports (T6): where a release stands, per org, product, feature and cycle.

A case's release status is its newest result in any cycle of the release, on the case's current
version. A result on an older version doesn't count: the case is `untested` and `stale`, so a release
can't look `ready` on case text that changed after the run, but its last result is still given. Live
cases of the release's features that are in no cycle are `untested` and `not_in_cycle`. Archived cases
are left out. `behind` is the one rule for "stale" in every report.

With no release (the whole product, or a feature's subtree), a case's status is its newest result in
the period in any cycle of the product, by the same rule. Trends count every result recorded in the
period, by day in the period's time zone.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
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
    DriftedCase,
    FeatureCaseStatus,
    FeatureCounts,
    FeatureKpis,
    FeatureReport,
    FeatureRun,
    LastResult,
    OrgKpis,
    OrgProduct,
    OrgReport,
    PeakDay,
    ProductReport,
    ProductWhole,
    ReleaseReport,
    ReleaseTotals,
    ReportCounts,
    ReportRelease,
    ResultActor,
    ScopeKpis,
    Trend,
    TrendDay,
)
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ
from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import (
    RELEASE_STATUSES,
    RESULT_STATUSES,
    Actor,
    CaseVersion,
    Cycle,
    CycleCase,
    Feature,
    Product,
    Release,
    ReleaseFeature,
    Result,
    TestCase,
)

router = APIRouter(tags=["reports"])

LISTED = ("planned", "in_progress", "released")  # a product report leaves out `cancelled` releases
DEFAULT_DAYS = 30
MAX_DAYS = 366
HISTORY_RUNS = 5


@dataclass
class Period:
    """The days `start` to `end`, both included, in `tz`."""

    start: date
    end: date
    tz: ZoneInfo

    @property
    def start_utc(self) -> datetime:
        return datetime.combine(self.start, time(), self.tz).astimezone(UTC)

    @property
    def end_utc(self) -> datetime:
        """The first moment after the period."""
        return datetime.combine(self.end + timedelta(days=1), time(), self.tz).astimezone(UTC)

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    def day(self, at: datetime) -> date:
        return aware(at).astimezone(self.tz).date()


def period(
    from_: date | None = Query(
        None, alias="from", description="First day, in `tz`; default 29 days before `to`"
    ),
    to: date | None = Query(None, description="Last day, in `tz`, included; default today"),
    tz: str = Query("UTC", description="An IANA time zone, e.g. America/Los_Angeles"),
) -> Period:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, f"Unknown time zone: {tz}") from None
    end = to or utcnow().astimezone(zone).date()
    start = from_ or end - timedelta(days=DEFAULT_DAYS - 1)
    if start > end:
        raise HTTPException(422, "from is after to")
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(422, f"A period is at most {MAX_DAYS} days")
    return Period(start, end, zone)


@dataclass
class CaseStatus:
    case: TestCase
    status: str = "untested"
    stale: bool = False
    not_in_cycle: bool = False
    cycle_id: str | None = None
    last_result_at: datetime | None = None
    last_result_status: str | None = None
    last_version: int | None = None  # the case version `last_result_status` ran on
    cc: CycleCase | None = None  # the cycle case that decides `status`
    last_cc: CycleCase | None = None  # the newest cycle case with a result, on any version
    result: Result | None = None
    last_result: Result | None = None


def behind(version: int, case: TestCase) -> bool:
    """Stale: `version` (a result's or a pin's) is older than the case's current version."""
    return version != case.current_version


def newest_results(db: Session, org_id: str, release: Release) -> dict[str, tuple[int, str]]:
    """(case_version, status) of the newest result of each cycle case in the release's cycles."""
    in_release = (
        select(CycleCase.id)
        .join(Cycle, and_(Cycle.org_id == CycleCase.org_id, Cycle.id == CycleCase.cycle_id))
        .where(CycleCase.org_id == org_id, Cycle.release_id == release.id)
    )
    newest = (
        select(Result.cycle_case_id, func.max(Result.attempt).label("attempt"))
        .where(Result.org_id == org_id, Result.cycle_case_id.in_(in_release))
        .group_by(Result.cycle_case_id)
        .subquery()
    )
    rows = db.execute(
        select(Result.cycle_case_id, Result.case_version, Result.status).join(
            newest,
            and_(
                Result.org_id == org_id,
                Result.cycle_case_id == newest.c.cycle_case_id,
                Result.attempt == newest.c.attempt,
            ),
        )
    )
    return {cc_id: (version, status) for cc_id, version, status in rows}


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
    newest = newest_results(db, org_id, release)
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
        if case.id in decided or cc.id not in newest:
            continue
        version, last_status = newest[cc.id]
        s.last_cc = s.last_cc or cc
        if behind(version, case):
            # Rows come newest first: the first stale one gives the last result.
            if not s.stale:
                s.stale, s.cycle_id = True, cc.cycle_id
                s.last_result_at, s.last_result_status, s.last_version = (
                    cc.last_result_at,
                    last_status,
                    version,
                )
            continue
        s.status, s.stale, s.cycle_id = cc.status, False, cc.cycle_id
        s.last_result_at, s.last_result_status, s.last_version = cc.last_result_at, last_status, version
        s.cc = cc
        decided.add(case.id)
    feature_ids = release_feature_ids(db, org_id, release)
    if feature_ids:
        for case in feature_candidates(db, org_id, release.product_id, feature_ids):
            if is_live(case) and case.id not in out:
                out[case.id] = CaseStatus(case, not_in_cycle=True)
    return out


def product_status(db: Session, org_id: str, product_id: str, per: Period) -> dict[str, CaseStatus]:
    """Each case's status in the whole product, by case id: its newest result in the period in any cycle
    of the product, on the current version. Live cases with no such result are `untested`."""
    rows = db.execute(
        select(Result, CycleCase, TestCase)
        .join(CycleCase, and_(CycleCase.org_id == Result.org_id, CycleCase.id == Result.cycle_case_id))
        .join(Cycle, and_(Cycle.org_id == CycleCase.org_id, Cycle.id == CycleCase.cycle_id))
        .join(TestCase, and_(TestCase.org_id == CycleCase.org_id, TestCase.id == CycleCase.case_id))
        .where(
            Result.org_id == org_id,
            Cycle.product_id == product_id,
            TestCase.archived_at.is_(None),
            Result.at >= per.start_utc,
            Result.at < per.end_utc,
        )
        .order_by(Result.at.desc(), Result.attempt.desc(), Result.id.desc())
    )
    out: dict[str, CaseStatus] = {}
    decided: set[str] = set()
    for res, cc, case in rows:
        s = out.setdefault(
            case.id,
            CaseStatus(
                case,
                cycle_id=cc.cycle_id,
                last_result_at=res.at,
                last_result_status=res.status,
                last_version=res.case_version,
                last_cc=cc,
                last_result=res,
            ),
        )
        if case.id in decided:
            continue
        if behind(res.case_version, case):
            s.stale = True
            continue
        s.status, s.stale, s.cycle_id, s.last_result_at = res.status, False, cc.cycle_id, res.at
        s.last_result_status, s.last_version = res.status, res.case_version
        s.cc, s.result = cc, res
        decided.add(case.id)
    live = select(TestCase).where(TestCase.org_id == org_id, TestCase.product_id == product_id)
    for case in db.scalars(live):
        if is_live(case) and case.id not in out:
            out[case.id] = CaseStatus(case)
    return out


def attach_results(db: Session, org_id: str, statuses: list[CaseStatus]) -> None:
    """Fill `result` and `last_result` from `cc` and `last_cc`: each cycle case's newest attempt."""
    cc_ids = {c.id for s in statuses for c in (s.cc, s.last_cc) if c is not None}
    if not cc_ids:
        return
    newest: dict[str, Result] = {}
    for res in db.scalars(
        select(Result)
        .where(Result.org_id == org_id, Result.cycle_case_id.in_(cc_ids))
        .order_by(Result.attempt.desc())
    ):
        newest.setdefault(res.cycle_case_id, res)
    for s in statuses:
        if s.cc is not None and s.result is None:
            s.result = newest.get(s.cc.id)
        if s.last_cc is not None and s.last_result is None:
            s.last_result = newest.get(s.last_cc.id)


def tally(statuses: list[CaseStatus]) -> ReportCounts:
    c = ReportCounts()
    for s in statuses:
        setattr(c, s.status, getattr(c, s.status) + 1)
        c.total += 1
        c.not_in_cycle += s.not_in_cycle
        c.stale += s.stale
    return c


def count_statuses(statuses: list[str]) -> ReportCounts:
    c = ReportCounts()
    for status in statuses:
        setattr(c, status, getattr(c, status) + 1)
        c.total += 1
    return c


def is_ready(c: ReportCounts) -> bool:
    return c.total > 0 and c.fail + c.error + c.untested == 0


def pct(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def ran(c: ReportCounts) -> int:
    """Cases (or results) that aren't `untested`: `ignore`, `skip` and `cancel` count as ran."""
    return c.total - c.untested


def success_rate(c: ReportCounts) -> int | None:
    return pct(c.success, ran(c))


def verdict(c: ReportCounts) -> str:
    """Drift is a risk: a case whose newest result is on an older version makes the row `at_risk`."""
    if c.fail or c.error or c.stale:
        return "at_risk"
    if ran(c) == 0:
        return "not_started"
    return "ready" if is_ready(c) else "in_progress"


def scope_kpis(c: ReportCounts) -> ScopeKpis:
    return ScopeKpis(
        cases=c.total,
        ran=ran(c),
        fail=c.fail,
        error=c.error,
        skip=c.skip,
        drift=c.stale,
        success_rate=success_rate(c),
    )


def release_out(r: Release) -> ReportRelease:
    return ReportRelease(id=r.id, version=r.version, name=r.name, status=r.status, product_id=r.product_id)


@dataclass
class ReleaseRows:
    counts: ReportCounts
    ready: bool
    features: list[FeatureCounts]


def feature_rows(
    db: Session, org_id: str, product_id: str, statuses: list[CaseStatus], wanted: set[str]
) -> ReleaseRows:
    """The totals, `ready`, and one row per feature: the one source for every report's `ready`.

    Rows start from the `wanted` (release) features, so a release feature with no case has a row
    (`total: 0`). A case counts once, in the row of its nearest wanted feature at or above its own
    feature; a case under no wanted feature counts in its own feature's row, with `in_release: false`.
    A row's `ready`, `drift` and `verdict` look at every case under the feature, so a release feature
    whose cases all sit in a listed sub-feature's row is covered. The whole is `ready` when its totals
    are and every wanted feature has at least one case under it. A wanted feature that has since been
    archived is retired: it needs no case, and gets a row only when a case counts in it.
    """
    features = {
        f.id: f
        for f in db.scalars(select(Feature).where(Feature.org_id == org_id, Feature.product_id == product_id))
    }
    product = db.get(Product, product_id)

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
        basis = under[f_id] if listed else cases
        whole = tally(basis)
        drifted = sorted(
            (s for s in basis if s.stale and s.last_version is not None), key=lambda s: s.case.number
        )
        return FeatureCounts(
            feature_id=f_id,
            name=f.name if f else "",
            in_release=listed,
            counts=tally(cases),
            ready=is_ready(whole),
            path=" › ".join(features[i].name for i in reversed(chain(f_id)) if i in features),
            drift=whole.stale,
            drifted=[
                DriftedCase(
                    key=case_key(product, s.case),
                    ran_version=s.last_version,
                    current_version=s.case.current_version,
                )
                for s in drifted
            ],
            verdict=verdict(whole),
        )

    out = sorted(
        (row(f_id, cases) for f_id, cases in rows.items()),
        key=lambda r: (not r.in_release, r.name, r.feature_id),
    )
    c = tally(statuses)
    return ReleaseRows(counts=c, ready=is_ready(c) and all(under[f_id] for f_id in required), features=out)


def release_rows(db: Session, org_id: str, release: Release) -> ReleaseRows:
    statuses = list(release_status(db, org_id, release).values())
    wanted = set(release_feature_ids(db, org_id, release))
    return feature_rows(db, org_id, release.product_id, statuses, wanted)


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


def period_results(db: Session, org_id: str, per: Period, *where) -> list:
    """The period's results as (at, status, actor kind, product id) rows, in cycles matching `where`."""
    return db.execute(
        select(Result.at, Result.status, Actor.kind, Cycle.product_id)
        .join(CycleCase, and_(CycleCase.org_id == Result.org_id, CycleCase.id == Result.cycle_case_id))
        .join(Cycle, and_(Cycle.org_id == CycleCase.org_id, Cycle.id == CycleCase.cycle_id))
        .outerjoin(Actor, and_(Actor.org_id == Result.org_id, Actor.id == Result.actor_id))
        .where(Result.org_id == org_id, Result.at >= per.start_utc, Result.at < per.end_utc, *where)
    ).all()


def trend(per: Period, rows: list) -> Trend:
    days = {d: TrendDay(date=d) for d in per.days()}
    total = agents = 0
    for at, status, kind, _ in rows:
        day = days.get(per.day(at))
        if day is None:
            continue
        setattr(day, status, getattr(day, status) + 1)
        total += 1
        agents += kind == "agent"
    peak: PeakDay | None = None
    for day in days.values():
        n = sum(getattr(day, s) for s in RESULT_STATUSES)
        if n and (peak is None or n > peak.total):
            peak = PeakDay(date=day.date, total=n)
    return Trend(days=list(days.values()), total=total, peak_day=peak, by_agents_pct=pct(agents, total))


@router.get(
    "/orgs/{org}/releases/{release_id}/report",
    response_model=ReleaseReport,
    **op("reports_release", READ, "reports"),
)
def reports_release(
    release_id: str,
    per: Period = Depends(period),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Release readiness: the counts, `ready`, one row per release feature (`in_release: true`, even with
    no cases), then rows for cases of features outside the release (`in_release: false`). Not ready while
    a release feature has no case. `trend` is the release's results in the period."""
    r = get_release(db, ctx, release_id)
    rr = release_rows(db, ctx.org.id, r)
    return ReleaseReport(
        release=release_out(r),
        counts=rr.counts,
        ready=rr.ready,
        features=rr.features,
        kpis=scope_kpis(rr.counts),
        trend=trend(per, period_results(db, ctx.org.id, per, Cycle.release_id == r.id)),
    )


@router.get(
    "/orgs/{org}/products/{product}/report",
    response_model=ProductReport,
    **op("reports_product", READ, "reports"),
)
def reports_product(
    product: str,
    release: str | None = Query(None, description="A release id; default every release that isn't cancelled"),
    per: Period = Depends(period),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """With `release`: that release's totals and its trend. Without: every listed release's totals, the
    product's trend, and `whole`, the product as it stands in the period with one row per feature."""
    p = get_product(db, ctx, product)
    org_id = ctx.org.id
    if release is not None:
        r = get_release(db, ctx, release)
        if r.product_id != p.id:
            raise HTTPException(422, f"Release {release} is not a release of {p.key}")
        return ProductReport(
            product_id=p.id,
            product_key=p.key,
            releases=[release_totals(db, org_id, r)],
            trend=trend(per, period_results(db, org_id, per, Cycle.release_id == r.id)),
        )
    rr = feature_rows(db, org_id, p.id, list(product_status(db, org_id, p.id, per).values()), set())
    return ProductReport(
        product_id=p.id,
        product_key=p.key,
        releases=[release_totals(db, org_id, r) for r in product_releases(db, org_id, p.id, LISTED)],
        trend=trend(per, period_results(db, org_id, per, Cycle.product_id == p.id)),
        whole=ProductWhole(counts=rr.counts, kpis=scope_kpis(rr.counts), features=rr.features),
    )


@router.get("/orgs/{org}/report", response_model=OrgReport, **op("reports_org", READ, "reports"))
def reports_org(
    release_status_: list[str] = Query(
        [], alias="release_status", description="Repeatable; default planned and in_progress"
    ),
    per: Period = Depends(period),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Every product the caller can see (not archived), with its releases in the given statuses, its live
    cases, open cycles and the period's results; the org's KPIs and trend over those products."""
    wanted = tuple(release_status_) or ("planned", "in_progress")
    bad = [s for s in wanted if s not in RELEASE_STATUSES]
    if bad:
        raise HTTPException(422, f"Unknown release_status: {', '.join(bad)}")
    org_id = ctx.org.id
    query = select(Product).where(Product.org_id == org_id, Product.archived_at.is_(None))
    if ctx.product_ids is not None:
        query = query.where(Product.id.in_(ctx.product_ids))
    products = list(db.scalars(query.order_by(Product.key)))
    ids = [p.id for p in products]

    cases = {p_id: [] for p_id in ids}
    for case in db.scalars(select(TestCase).where(TestCase.org_id == org_id, TestCase.product_id.in_(ids))):
        if is_live(case):
            cases[case.product_id].append(case)
    open_cycles = dict(
        db.execute(
            select(Cycle.product_id, func.count())
            .where(Cycle.org_id == org_id, Cycle.product_id.in_(ids), Cycle.status == "open")
            .group_by(Cycle.product_id)
        ).all()
    )
    open_untested = dict(
        db.execute(
            select(Cycle.product_id, func.count())
            .select_from(CycleCase)
            .join(Cycle, and_(Cycle.org_id == CycleCase.org_id, Cycle.id == CycleCase.cycle_id))
            .where(
                CycleCase.org_id == org_id,
                Cycle.product_id.in_(ids),
                Cycle.status == "open",
                CycleCase.status == "untested",
            )
            .group_by(Cycle.product_id)
        ).all()
    )
    rows = period_results(db, org_id, per, Cycle.product_id.in_(ids))
    by_product: dict[str, list[str]] = {p_id: [] for p_id in ids}
    for _, status, _, p_id in rows:
        by_product[p_id].append(status)

    out = []
    for p in products:
        results = count_statuses(by_product[p.id])
        results.untested = open_untested.get(p.id, 0)
        results.total += results.untested
        live = cases[p.id]
        out.append(
            OrgProduct(
                product_id=p.id,
                product_key=p.key,
                releases=[release_totals(db, org_id, r) for r in product_releases(db, org_id, p.id, wanted)],
                name=p.name,
                cases=len(live),
                automated_pct=pct(sum(c.automation == "automated" for c in live), len(live)),
                results=results,
                success_rate=success_rate(results),
                open_cycles=open_cycles.get(p.id, 0),
            )
        )
    every = [c for live in cases.values() for c in live]
    kpis = OrgKpis(
        ready_cases=sum(c.status == "ready" for c in every),
        products=len(products),
        success_rate=success_rate(count_statuses([status for _, status, _, _ in rows])),
        automated_pct=pct(sum(c.automation == "automated" for c in every), len(every)),
        open_cycles=sum(open_cycles.values()),
        open_untested=sum(open_untested.values()),
    )
    return OrgReport(products=out, kpis=kpis, trend=trend(per, rows))


def feature_history(db: Session, org_id: str, tree: set[str]) -> list[FeatureRun]:
    """The last cycles with a result for a case of the subtree, newest first, whatever the period."""
    newest = func.max(Result.at)
    runs = db.execute(
        select(CycleCase.cycle_id, newest)
        .select_from(Result)
        .join(CycleCase, and_(CycleCase.org_id == Result.org_id, CycleCase.id == Result.cycle_case_id))
        .join(TestCase, and_(TestCase.org_id == CycleCase.org_id, TestCase.id == CycleCase.case_id))
        .where(Result.org_id == org_id, TestCase.feature_id.in_(tree), TestCase.archived_at.is_(None))
        .group_by(CycleCase.cycle_id)
        .order_by(newest.desc(), CycleCase.cycle_id.desc())
        .limit(HISTORY_RUNS)
    ).all()
    if not runs:
        return []
    cycle_ids = [cycle_id for cycle_id, _ in runs]
    statuses: dict[str, list[str]] = {cycle_id: [] for cycle_id in cycle_ids}
    for cycle_id, status in db.execute(
        select(CycleCase.cycle_id, CycleCase.status)
        .join(TestCase, and_(TestCase.org_id == CycleCase.org_id, TestCase.id == CycleCase.case_id))
        .where(
            CycleCase.org_id == org_id,
            CycleCase.cycle_id.in_(cycle_ids),
            TestCase.feature_id.in_(tree),
            TestCase.archived_at.is_(None),
        )
    ):
        statuses[cycle_id].append(status)
    cycles = {
        cy.id: cy for cy in db.scalars(select(Cycle).where(Cycle.org_id == org_id, Cycle.id.in_(cycle_ids)))
    }
    release_ids = {cy.release_id for cy in cycles.values() if cy.release_id}
    versions = dict(
        db.execute(
            select(Release.id, Release.version).where(Release.org_id == org_id, Release.id.in_(release_ids))
        ).all()
    )
    out = []
    for cycle_id, at in runs:
        cy = cycles[cycle_id]
        c = count_statuses(statuses[cycle_id])
        out.append(
            FeatureRun(
                cycle_id=cy.id,
                release_version=versions.get(cy.release_id),
                environment=cy.environment,
                status=cy.status,
                at=at,
                counts=c,
                success_rate=success_rate(c),
            )
        )
    return out


@router.get(
    "/orgs/{org}/features/{feature_id}/report",
    response_model=FeatureReport,
    **op("reports_feature", READ, "reports"),
)
def reports_feature(
    feature_id: str,
    release: str | None = Query(
        None, description="A release id of the feature's product; default the whole product"
    ),
    per: Period = Depends(period),
    params: PageParams = Depends(page_params),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """The feature subtree's cases in the release (or, with no release, in the period): totals, one page of
    cases by case number, and the subtree's last 5 runs."""
    org_id = ctx.org.id
    f = get_feature(db, ctx, feature_id)
    r = None
    if release is not None:
        r = get_release(db, ctx, release)
        if r.product_id != f.product_id:
            raise HTTPException(422, f"Release {release} is not a release of the feature's product")
    tree = subtree(db, org_id, f.product_id, [f.id])
    every = release_status(db, org_id, r) if r is not None else product_status(db, org_id, f.product_id, per)
    statuses = sorted((s for s in every.values() if s.case.feature_id in tree), key=lambda s: s.case.number)
    after = int(params.cursor) if params.cursor and params.cursor.isdigit() else 0
    rest = [s for s in statuses if s.case.number > after]
    page = rest[: params.limit]
    cursor = str(page[-1].case.number) if len(rest) > params.limit else None
    attach_results(db, org_id, page)
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
    actor_ids = {res.actor_id for s in page for res in (s.result, s.last_result) if res is not None}
    actors = {
        a.id: ResultActor(kind=a.kind, name=a.name)
        for a in db.scalars(select(Actor).where(Actor.org_id == org_id, Actor.id.in_(actor_ids)))
    }

    def item(s: CaseStatus) -> FeatureCaseStatus:
        res, last = s.result, s.last_result
        return FeatureCaseStatus(
            id=s.case.id,
            key=case_key(p, s.case),
            title=titles.get(s.case.id, ""),
            feature_id=s.case.feature_id,
            status=s.status,
            stale=s.stale,
            cycle_id=s.cycle_id,
            last_result_at=s.last_result_at,
            last_result_status=s.last_result_status,
            ran_version=res.case_version if res else None,
            current_version=s.case.current_version,
            actor=actors.get(res.actor_id) if res else None,
            attempt=res.attempt if res else None,
            comment=(res.comment_text or None) if res else None,
            defects=res.defects if res else [],
            last_result=LastResult(
                status=last.status,
                version=last.case_version,
                at=last.at,
                actor=actors.get(last.actor_id),
                attempt=last.attempt,
            )
            if last is not None
            else None,
        )

    counts = tally(statuses)
    history = feature_history(db, org_id, tree)
    last5 = ReportCounts()
    for run in history:
        for name in ReportCounts.model_fields:
            setattr(last5, name, getattr(last5, name) + getattr(run.counts, name))
    return FeatureReport(
        feature_id=f.id,
        release=release_out(r) if r is not None else None,
        counts=counts,
        items=[item(s) for s in page],
        next_cursor=cursor,
        kpis=FeatureKpis(
            cases=counts.total,
            success=counts.success,
            success_rate_last5=success_rate(last5),
            drift=counts.stale,
        ),
        history=history,
    )


@router.get(
    "/orgs/{org}/cycles/{cycle_id}/report", response_model=CycleReport, **op("reports_cycle", READ, "reports")
)
def reports_cycle(
    cycle_id: str,
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """One cycle's counts by pinned status, and `stale`: its live cases pinned behind the current version.
    A case refreshed to the current version but not rerun yet counts as `untested`, not `stale`."""
    cy = get_cycle(db, ctx, cycle_id)
    c = cycle_counts(db, [cy.id])[cy.id]
    rows = db.execute(
        select(CycleCase.case_version, TestCase)
        .join(TestCase, and_(TestCase.org_id == CycleCase.org_id, TestCase.id == CycleCase.case_id))
        .where(CycleCase.org_id == ctx.org.id, CycleCase.cycle_id == cy.id, TestCase.archived_at.is_(None))
    )
    stale = sum(behind(version, case) for version, case in rows)
    return CycleReport(cycle_id=cy.id, counts=c, total=sum(c.values()), stale=stale)
