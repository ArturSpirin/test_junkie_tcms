"""Request and response bodies for execution (T4): cycles, bulk cycles, results and attachments."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from test_junkie_tcms.api.v1.schemas import Link, Name, Out, Patch, RichIn, RichOut, StepOut, UtcDateTime

CycleCaseStatus = Literal["untested", "success", "fail", "error", "ignore", "skip", "cancel"]
ResultStatus = Literal["success", "fail", "error", "ignore", "skip", "cancel"]
StepStatus = Literal["untested", "success", "fail", "error", "skip"]
Environment = Field(None, max_length=64)


class CycleSource(BaseModel):
    """At most one source: a whole product, an active plan, features (with sub-features), or cases (each a
    case key like PAY-12, or an id)."""

    model_config = ConfigDict(extra="forbid")
    product_id: str | None = None
    plan_id: str | None = None
    feature_ids: list[str] | None = Field(None, max_length=200)
    case_ids: list[str] | None = Field(None, max_length=1000)
    # automated and both send cases with a known automation_ref to these online consumers (T8).
    mode: Literal["manual", "automated", "both"] = "manual"
    consumer_ids: list[str] | None = Field(None, max_length=50)


class CycleCreate(CycleSource):
    name: str = Name
    environment: str | None = Environment
    release_id: str | None = None
    default_assignee_actor_id: str | None = None


class CycleUpdate(Patch):
    name: str | None = Field(None, min_length=1, max_length=200)
    environment: str | None = Environment
    default_assignee_actor_id: str | None = None


class CycleOut(BaseModel):
    id: str
    product_id: str
    release_id: str | None
    plan_id: str | None
    batch_id: str | None
    feature_id: str | None
    name: str
    environment: str | None
    status: str
    mode: str
    default_assignee_actor_id: str | None
    started_at: UtcDateTime
    closed_at: UtcDateTime | None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    counts: dict[str, int]


class PreviewFeature(BaseModel):
    feature_id: str
    name: str
    cases: int


class PreviewConsumer(BaseModel):
    consumer_id: str
    name: str
    cases: int
    jobs: int


class PreviewRunners(BaseModel):
    person: int
    consumers: list[PreviewConsumer]


class CyclePreviewOut(BaseModel):
    total: int
    features: list[PreviewFeature]
    skipped: dict[str, int]
    runners: PreviewRunners
    # Automated cases no chosen consumer has in its inventory; they go to people.
    unmatched: int


class CycleCasesAdd(BaseModel):
    """Cases to add, each a case key like PAY-12, or an id."""

    model_config = ConfigDict(extra="forbid")
    case_ids: list[str] = Field(min_length=1, max_length=1000)


class CycleCasesAdded(BaseModel):
    added: list[str]
    already_present: list[str]


class CycleCaseAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignee_actor_id: str | None


class CycleCaseOut(BaseModel):
    id: str
    cycle_id: str
    case_id: str
    key: str
    case_version: int
    current_version: int
    status: str
    assignee_actor_id: str | None
    position: int
    last_result_at: UtcDateTime | None
    runner: str
    consumer_id: str | None
    title: str
    steps: list[StepOut]


class CaseCycleOut(BaseModel):
    """A cycle a case is in, with the version the cycle pinned and the case's status there."""

    cycle_id: str
    name: str
    cycle_status: str
    environment: str | None
    started_at: UtcDateTime
    closed_at: UtcDateTime | None
    cycle_case_id: str
    case_version: int
    status: str
    last_result_at: UtcDateTime | None


class BulkCycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["features", "plans"] = "features"
    plan_ids: list[str] | None = Field(None, max_length=200)
    name: str | None = Field(None, min_length=1, max_length=200)
    environment: str | None = Environment


class CycleBatchOut(BaseModel):
    id: str
    product_id: str
    release_id: str
    name: str
    mode: str
    environment: str | None
    created_at: UtcDateTime
    cycles: list[CycleOut]


class StepResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str
    status: StepStatus
    actual: RichIn | None = None
    attachment_ids: list[str] = Field(default_factory=list, max_length=50)


class ResultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ResultStatus
    comment: RichIn | None = None
    duration_ms: int | None = Field(None, ge=0)
    steps: list[StepResultIn] = Field(default_factory=list, max_length=200)
    attachment_ids: list[str] = Field(default_factory=list, max_length=50)
    defects: list[Link] = Field(default_factory=list, max_length=50)


class StepResultOut(BaseModel):
    step_id: str
    status: str
    actual: RichOut
    attachment_ids: list[str]


class ResultOut(BaseModel):
    id: str
    cycle_case_id: str
    attempt: int
    status: str
    actor_id: str
    via: str
    comment: RichOut
    duration_ms: int | None
    steps: list[StepResultOut]
    attachment_ids: list[str]
    defects: list[dict[str, Any]]
    at: UtcDateTime


class BulkResultItem(BaseModel):
    """One result matched by `case_key` (e.g. PAY-12) or the pinned version's `automation_ref`."""

    model_config = ConfigDict(extra="forbid")
    case_key: str | None = Field(None, max_length=40)
    automation_ref: str | None = Field(None, max_length=500)
    status: ResultStatus
    comment: str | None = Field(None, max_length=20_000)
    duration_ms: int | None = Field(None, ge=0)
    defects: list[Link] = Field(default_factory=list, max_length=50)


class BulkResultsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BulkResultItem] = Field(min_length=1, max_length=500)


class BulkResultRow(BaseModel):
    index: int
    cycle_case_id: str
    result_id: str
    attempt: int


class BulkUnmatched(BaseModel):
    index: int
    case_key: str | None
    automation_ref: str | None


class BulkResultsOut(BaseModel):
    created: list[BulkResultRow]
    unmatched: list[BulkUnmatched]


class JobOut(BaseModel):
    id: str
    cycle_id: str
    consumer_id: str
    project: str
    refs: list[str]
    status: str
    timeout_s: int
    attempts: int
    claimed_at: UtcDateTime | None
    last_beat_at: UtcDateTime | None
    finished_at: UtcDateTime | None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class JobResultItem(BaseModel):
    """One result for a ref of the job, matched to the case whose pinned version has that automation_ref."""

    model_config = ConfigDict(extra="forbid")
    ref: str = Field(min_length=1, max_length=500)
    status: ResultStatus
    duration_ms: int | None = Field(None, ge=0)
    comment: str | None = Field(None, max_length=20_000)


class JobReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["running", "done", "failed"]
    results: list[JobResultItem] = Field(default_factory=list, max_length=500)


class JobReportOut(BaseModel):
    job: JobOut
    recorded: int
    unmatched: list[str]


class JobReassign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consumer_id: str


class AttachmentOut(Out):
    id: str
    product_id: str
    sha256: str
    filename: str
    mime: str
    size: int
    created_at: UtcDateTime


class AttachmentBase64In(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    mime: str = Field("application/octet-stream", max_length=127)
    # 5 MB decoded is about 6.7 MB of base64.
    content_base64: str = Field(max_length=7_000_000)
