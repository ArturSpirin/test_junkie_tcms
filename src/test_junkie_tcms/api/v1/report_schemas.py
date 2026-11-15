"""Request and response bodies for reports, search and CSV import/export (T6)."""

from typing import Any, Literal

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
    feature_id: str
    name: str
    counts: ReportCounts


class ReleaseReport(BaseModel):
    """`ready`: at least one case, and none `fail`, `error` or `untested`."""

    release: ReportRelease
    counts: ReportCounts
    ready: bool
    features: list[FeatureCounts]


class ReleaseTotals(BaseModel):
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
    matched_in: list[Literal["title", "preconditions", "steps"]]


class ExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["csv", "md-bundle"] = "csv"
    feature: str | None = Field(None, description="A feature id; its subtree is exported")
    include_archived: bool = False


class ImportIn(BaseModel):
    """`csv` must have the header `exports_create` writes. `mapping` is reserved for column mapping and
    is refused for now."""

    model_config = ConfigDict(extra="forbid")
    csv: str
    create_features: bool = Field(False, description="Create missing features named in the `feature` path")
    dry_run: bool = Field(False, description="Check every row and report the counts, but write nothing")
    mapping: dict[str, Any] | None = Field(None, description="Not supported yet")


class ImportOut(BaseModel):
    created: int
    updated: int
    unchanged: int
    keys: list[str]
    dry_run: bool
