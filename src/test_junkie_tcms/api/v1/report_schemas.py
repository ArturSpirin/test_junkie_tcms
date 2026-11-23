"""Request and response bodies for reports, search and CSV import/export (T6)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from test_junkie_tcms.api.v1.execution_schemas import CycleCaseStatus
from test_junkie_tcms.api.v1.schemas import UtcDateTime


class ReportCounts(BaseModel):
    """Cases by release status. `untested` includes `not_in_cycle` (live cases of an affected feature in
    no cycle of the release) and `stale` (cases whose only results are on an older case version)."""

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


class FeatureCounts(BaseModel):
    """One feature's row. A case counts in its nearest release feature; `in_release: false` rows hold
    cases a cycle of the release pulled in from features outside it. `ready`: the cases under the
    feature (sub-features included) number at least one, and none is `fail`, `error` or `untested`."""

    feature_id: str
    name: str
    in_release: bool
    counts: ReportCounts
    ready: bool


class ReleaseReport(BaseModel):
    """`ready`: at least one case, none `fail`, `error` or `untested`, and every release feature (not
    archived) has at least one case under it. `features` lists the release's features first, a feature
    with no case included, then any features outside the release."""

    release: ReportRelease
    counts: ReportCounts
    ready: bool
    features: list[FeatureCounts]


class ReleaseTotals(BaseModel):
    """`ready` as in `ReleaseReport`."""

    release: ReportRelease
    counts: ReportCounts
    ready: bool


class ProductReport(BaseModel):
    product_id: str
    product_key: str
    releases: list[ReleaseTotals]


class OrgReport(BaseModel):
    products: list[ProductReport]


class FeatureCaseStatus(BaseModel):
    id: str
    key: str
    title: str
    feature_id: str
    status: CycleCaseStatus
    stale: bool
    cycle_id: str | None
    last_result_at: UtcDateTime | None


class FeatureReport(BaseModel):
    """Totals for the whole subtree; `items` is one page of its cases, by case number."""

    feature_id: str
    release: ReportRelease
    counts: ReportCounts
    items: list[FeatureCaseStatus]
    next_cursor: str | None = None


class CycleReport(BaseModel):
    cycle_id: str
    counts: dict[str, int]
    total: int


class SearchHit(BaseModel):
    id: str
    key: str
    product_id: str
    feature_id: str
    title: str
    current_version: int
    matched_in: list[Literal["title", "description", "preconditions", "steps"]]


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
