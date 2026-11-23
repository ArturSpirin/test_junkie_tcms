"""Request and response bodies for reports, search and CSV import/export (T6)."""

from datetime import date as date_
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from test_junkie_tcms.api.v1.execution_schemas import CycleCaseStatus
from test_junkie_tcms.api.v1.schemas import UtcDateTime


class ReportCounts(BaseModel):
    """Cases by release status. `untested` includes `not_in_cycle` (live cases of an affected feature in
    no cycle of the release) and `stale` (cases whose newest result ran on an older case version)."""

    untested: int = 0
    success: int = 0
    fail: int = 0
    error: int = 0
    ignore: int = 0
    skip: int = 0
    cancel: int = 0
    total: int = 0
    not_in_cycle: int = 0
    stale: int = 0


class ReportRelease(BaseModel):
    id: str
    version: str
    name: str
    status: str
    product_id: str


Verdict = Literal["ready", "at_risk", "in_progress", "not_started"]


class TrendDay(BaseModel):
    date: date_
    success: int = 0
    fail: int = 0
    error: int = 0
    ignore: int = 0
    skip: int = 0
    cancel: int = 0


class PeakDay(BaseModel):
    date: date_
    total: int


class Trend(BaseModel):
    """Every result recorded in the period (each attempt counts), by day in the period's `tz`. Every day of
    the period is listed, a day with no result as zeros. `peak_day` is the first day with the most results,
    null with none; `by_agents_pct` is the whole percent recorded by agent actors, null with none."""

    days: list[TrendDay]
    total: int
    peak_day: PeakDay | None
    by_agents_pct: int | None


class ScopeKpis(BaseModel):
    """`cases` is `counts.total`; `ran` is the cases that aren't `untested`; `success_rate` is the whole
    percent `success / ran` (`ignore`, `skip` and `cancel` count as ran), null when nothing ran; `drift` is
    the cases whose newest result is on an older case version (`counts.stale`)."""

    cases: int
    ran: int
    fail: int
    error: int
    skip: int
    drift: int
    success_rate: int | None


class DriftedCase(BaseModel):
    key: str
    ran_version: int
    current_version: int


class FeatureCounts(BaseModel):
    """One feature's row. A case counts in its nearest release feature; `in_release: false` rows hold
    cases a cycle of the release pulled in from features outside it. `ready`: the cases under the
    feature (sub-features included) number at least one, and none is `fail`, `error` or `untested`.
    `path` is the feature's names from the top, joined with ` › `. `drift`, `drifted` and `verdict` look at
    the same cases as `ready`. `verdict`: `at_risk` with any `fail`, `error` or drift, else `not_started` when
    nothing ran, else `ready` when `ready`, else `in_progress`."""

    feature_id: str
    name: str
    in_release: bool
    counts: ReportCounts
    ready: bool
    path: str = ""
    drift: int = 0
    drifted: list[DriftedCase] = []
    verdict: Verdict = "not_started"


class ReleaseReport(BaseModel):
    """`ready`: at least one case, none `fail`, `error` or `untested`, and every release feature (not
    archived) has at least one case under it. `features` lists the release's features first, a feature
    with no case included, then any features outside the release. `kpis` and `features` are as the
    release stands; `trend` is the results in the release's cycles in the period."""

    release: ReportRelease
    counts: ReportCounts
    ready: bool
    features: list[FeatureCounts]
    kpis: ScopeKpis
    trend: Trend


class ReleaseTotals(BaseModel):
    """`ready` as in `ReleaseReport`."""

    release: ReportRelease
    counts: ReportCounts
    ready: bool


class ProductWhole(BaseModel):
    """The whole product, no release: each live case's status is its newest result in the period in any
    cycle of the product, on the case's current version (`stale` and `untested` otherwise, as in a release).
    `features` has one row per feature with a live case, `in_release: false`."""

    counts: ReportCounts
    kpis: ScopeKpis
    features: list[FeatureCounts]


class ProductReport(BaseModel):
    """`trend`: results in the period, in the given release's cycles, else in every cycle of the product.
    `whole` is set only when no `release` is given."""

    product_id: str
    product_key: str
    releases: list[ReleaseTotals]
    trend: Trend | None = None
    whole: ProductWhole | None = None


class OrgKpis(BaseModel):
    """Over the products in `products`. `ready_cases`: live cases with status `ready`. `success_rate`: the
    whole percent `success / ran` over the period's results. `automated_pct`: live cases with automation
    `automated`. `open_cycles` and `open_untested` (their `untested` cases) are as of now, not the period."""

    ready_cases: int
    products: int
    success_rate: int | None
    automated_pct: int | None
    open_cycles: int
    open_untested: int


class OrgProduct(BaseModel):
    """`releases` as in `ProductReport`. `results`: the period's results by status, `untested` being the
    `untested` cases in the product's open cycles now; `success_rate` is over it."""

    product_id: str
    product_key: str
    releases: list[ReleaseTotals]
    name: str
    cases: int
    automated_pct: int | None
    results: ReportCounts
    success_rate: int | None
    open_cycles: int


class OrgReport(BaseModel):
    products: list[OrgProduct]
    kpis: OrgKpis
    trend: Trend


class ResultActor(BaseModel):
    kind: str
    name: str


class LastResult(BaseModel):
    """The case's newest result in scope, on any case version (a stale case's too)."""

    status: str
    version: int
    at: UtcDateTime
    actor: ResultActor | None
    attempt: int


class FeatureCaseStatus(BaseModel):
    """A `stale` case is `untested`; `last_result_at` and `last_result_status` still give its last result,
    on the older version, until a rerun on the current one. `status` and the fields from `ran_version` to
    `defects` come from the result that decides it, null or empty while `untested`. `last_result` is the
    newest result even when it is on an older version."""

    id: str
    key: str
    title: str
    feature_id: str
    status: CycleCaseStatus
    stale: bool
    cycle_id: str | None
    last_result_at: UtcDateTime | None
    last_result_status: str | None = None
    ran_version: int | None = None
    current_version: int = 1
    actor: ResultActor | None = None
    attempt: int | None = None
    comment: str | None = None
    defects: list[dict] = []
    last_result: LastResult | None = None


class FeatureRun(BaseModel):
    """One cycle with a result for a case of the subtree: `counts` are those cases' statuses in the cycle
    now, `at` its newest result for them."""

    cycle_id: str
    release_version: str | None
    environment: str | None
    status: str
    at: UtcDateTime
    counts: ReportCounts
    success_rate: int | None


class FeatureKpis(BaseModel):
    """`success_rate_last5` is `success / ran` over the summed `history` counts."""

    cases: int
    success: int
    success_rate_last5: int | None
    drift: int


class FeatureReport(BaseModel):
    """Totals for the whole subtree; `items` is one page of its cases, by case number. With no `release`,
    statuses are as in `ProductWhole`. `history` is the last 5 cycles with a result for the subtree, newest
    first, whatever the period."""

    feature_id: str
    release: ReportRelease | None
    counts: ReportCounts
    items: list[FeatureCaseStatus]
    next_cursor: str | None = None
    kpis: FeatureKpis
    history: list[FeatureRun]


class CycleReport(BaseModel):
    """`counts` are by pinned status. `stale`: live cases pinned to an older version than the case's
    current one (refresh and retest them)."""

    cycle_id: str
    counts: dict[str, int]
    total: int
    stale: int = 0


class SearchHit(BaseModel):
    id: str
    key: str
    product_id: str
    feature_id: str
    title: str
    current_version: int
    matched_in: list[Literal["title", "preconditions", "steps"]]


class ExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["csv", "md-bundle"] = "csv"
    feature: str | None = Field(None, description="A feature id; its subtree is exported")
    include_archived: bool = False


class ImportIn(BaseModel):
    """`format: csv` takes `csv`, with the header `exports_create` writes unless `mapping` renames it.
    `format: md-bundle` takes `bundle`, the export's zip as base64."""

    model_config = ConfigDict(extra="forbid")
    format: Literal["csv", "md-bundle"] = "csv"
    csv: str | None = None
    bundle: str | None = Field(None, description="An md-bundle zip, base64 (format md-bundle)")
    create_features: bool = Field(False, description="Create missing features named in the `feature` path")
    dry_run: bool = Field(False, description="Check every row and report the counts, but write nothing")
    mapping: dict[str, str | None] | None = Field(
        None,
        description="Their column name -> ours (or step_action, step_expected), or null to skip it. Every "
        "column must be mapped, skipped or already one of ours; with a mapping, tags may be comma-separated",
    )


class ImportOut(BaseModel):
    created: int
    updated: int
    unchanged: int
    keys: list[str]
    dry_run: bool
