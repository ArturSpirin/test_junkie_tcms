from datetime import date, datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from test_junkie_tcms.db.base import aware

# A stored time read back from SQLite is naive; mark it UTC so the API always says so.
UtcDateTime = Annotated[datetime, AfterValidator(aware)]

Role = Literal["viewer", "tester", "editor", "admin", "owner"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):  # noqa: UP046 - PEP 695 needs 3.12; we support 3.11
    items: list[T]
    next_cursor: str | None = None


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1000)


class MeOrg(BaseModel):
    slug: str
    name: str
    role: str


class MeOut(BaseModel):
    via: str
    user_id: str | None = None
    email: str | None = None
    name: str | None = None
    actor_id: str | None = None
    token_id: str | None = None
    orgs: list[MeOrg] = []


class OrgOut(Out):
    id: str
    slug: str
    name: str
    created_at: datetime


class OrgUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberOut(BaseModel):
    user_id: str
    actor_id: str
    email: str
    name: str
    role: str
    removed_at: datetime | None = None


class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    role: Role
    # Only used when the email has no account yet.
    password: str | None = Field(None, min_length=8, max_length=1000)


class MemberUpdate(BaseModel):
    role: Role


class AgentOut(Out):
    id: str
    name: str
    role: str
    owner_user_id: str
    disabled_at: datetime | None = None
    created_at: datetime


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: Role
    # Defaults to the calling user.
    owner_user_id: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    role: Role | None = None


class TokenOut(Out):
    id: str
    name: str
    prefix: str
    actor_id: str
    scopes: list[str]
    product_ids: list[str] | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1)
    # Defaults to the caller's own actor.
    actor_id: str | None = None
    expires_at: datetime | None = None
    # Limit the token to these products; None means every product (or the caller's own limit).
    product_ids: list[str] | None = None


class TokenCreated(TokenOut):
    token: str = Field(description="Shown once; store it now")


## Catalog (T2)

# A rich field is written as {"markdown": "..."} or {"doc": {...}} and read per ?rich=:
# a Markdown string (default), the doc, or {"markdown", "doc"} for rich=both.
RichOut = str | dict[str, Any]
RichMode = Literal["markdown", "doc", "both"]


class MarkdownIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    markdown: str = Field(max_length=200_000)


class DocIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc: dict[str, Any] = Field(description="A rich text doc (TipTap StarterKit node names)")


RichIn = MarkdownIn | DocIn
Name = Field(min_length=1, max_length=200)


class Patch(BaseModel):
    """PATCH bodies: unknown fields are refused, so an immutable field can't look updated."""

    model_config = ConfigDict(extra="forbid")


class ProductOut(BaseModel):
    id: str
    key: str
    name: str
    description: RichOut
    archived_at: UtcDateTime | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ProductCreate(BaseModel):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$", description="Short key, e.g. PAY; can't change later")
    name: str = Name
    description: RichIn | None = None


class ProductUpdate(Patch):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: RichIn | None = None


class FeatureOut(BaseModel):
    id: str
    product_id: str
    parent_id: str | None = None
    name: str
    description: RichOut
    owner_actor_id: str | None = None
    position: int
    archived_at: UtcDateTime | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ActorRef(BaseModel):
    id: str
    name: str
    kind: str


class FeatureNode(FeatureOut):
    # From the feature's latest audit event; null when it has none.
    updated_by: ActorRef | None = None
    children: list["FeatureNode"] = []


class FeatureTree(BaseModel):
    items: list[FeatureNode]


class FeatureCreate(BaseModel):
    name: str = Name
    description: RichIn | None = None
    parent_id: str | None = None
    owner_actor_id: str | None = None


class FeatureUpdate(Patch):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: RichIn | None = None
    owner_actor_id: str | None = None


class FeatureMove(BaseModel):
    parent_id: str | None = Field(None, description="New parent; null moves it to the top level")
    position: int = Field(ge=0, description="Index among its new siblings; past the end appends")


ReleaseStatus = Literal["planned", "in_progress", "released", "cancelled"]


class ReleaseOut(BaseModel):
    id: str
    product_id: str
    version: str
    name: str
    status: str
    target_date: date | None = None
    released_at: UtcDateTime | None = None
    notes: RichOut
    feature_ids: list[str]
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ReleaseCreate(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    name: str = Name
    status: ReleaseStatus = "planned"
    target_date: date | None = None
    released_at: datetime | None = None
    notes: RichIn | None = None


class ReleaseUpdate(Patch):
    version: str | None = Field(None, min_length=1, max_length=64)
    name: str | None = Field(None, min_length=1, max_length=200)
    status: ReleaseStatus | None = None
    target_date: date | None = None
    released_at: datetime | None = None
    notes: RichIn | None = None


class ReleaseFeaturesIn(BaseModel):
    feature_ids: list[str] = Field(max_length=2000)


class PlanQuery(BaseModel):
    """Selects cases by their fields; T3 resolves it."""

    model_config = ConfigDict(extra="forbid")
    tags: list[str] = Field([], max_length=50)
    priority: list[str] = Field([], max_length=10)
    type: list[str] = Field([], max_length=10)
    automation: list[str] = Field([], max_length=10)


class PlanEntryIn(BaseModel):
    """Exactly one of `case_id`, `feature_id`, `query` or `release_id`. A `release_id` adds one feature entry
    per feature of that release at write time; the release itself is not stored."""

    model_config = ConfigDict(extra="forbid")
    case_id: str | None = None
    feature_id: str | None = None
    query: PlanQuery | None = None
    release_id: str | None = None


class PlanEntriesIn(BaseModel):
    entries: list[PlanEntryIn] = Field(min_length=1, max_length=500)


class PlanEntriesOrder(BaseModel):
    """Every current entry id of the plan, in the new order."""

    entry_ids: list[str] = Field(max_length=5000)


class PlanEntryOut(Out):
    id: str
    case_id: str | None = None
    feature_id: str | None = None
    query: dict[str, Any] | None = None
    position: int


class PlanOut(BaseModel):
    id: str
    product_id: str
    release_id: str | None = None
    name: str
    description: RichOut
    status: str
    entries: list[PlanEntryOut]
    created_at: UtcDateTime
    updated_at: UtcDateTime


class PlanCreate(BaseModel):
    name: str = Name
    description: RichIn | None = None
    release_id: str | None = None


class PlanUpdate(Patch):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: RichIn | None = None
    release_id: str | None = None
    status: Literal["draft", "active", "archived"] | None = None


class ResolvedCase(BaseModel):
    id: str
    key: str
    version: int
    title: str


class PlanResolved(BaseModel):
    plan_id: str
    items: list[ResolvedCase]


## Cases (T3)

CaseStatus = Literal["draft", "ready", "deprecated"]
Automation = Literal["manual", "automated", "to_automate"]
Priority = Literal["low", "medium", "high", "critical"]
CaseType = Literal["functional", "regression", "smoke", "acceptance", "performance", "security", "other"]
Title = Field(min_length=1, max_length=500)
ChangeNote = Field(None, max_length=500)


class StepIn(BaseModel):
    """A step without `id` is new; one with an `id` keeps it from the current version, so reordering is
    sending the same ids in a new order."""

    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    action: RichIn
    expected: RichIn | None = None


class StepOut(BaseModel):
    id: str
    action: RichOut
    expected: RichOut


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(pattern=r"^https?://", max_length=2000)
    key: str | None = Field(None, max_length=100)


class CaseFields(BaseModel):
    """The versioned content; on an update, a field left out keeps its current value."""

    model_config = ConfigDict(extra="forbid")
    preconditions: RichIn | None = None
    steps: list[StepIn] | None = Field(None, max_length=200)
    priority: Priority | None = None
    type: CaseType | None = None
    status: CaseStatus | None = None
    automation: Automation | None = None
    automation_ref: str | None = Field(None, max_length=500)
    links: list[Link] | None = Field(None, max_length=50)
    custom: dict[str, Any] | None = Field(None, description="Free-form, for plugins; at most 16 KB as JSON")
    tags: list[str] | None = Field(
        None, max_length=50, description="Names; made lowercase, created on first use"
    )
    change_note: str | None = ChangeNote


class CaseCreate(CaseFields):
    feature_id: str
    title: str = Title


class CaseUpdate(CaseFields):
    title: str | None = Field(None, min_length=1, max_length=500)


class CaseOut(BaseModel):
    id: str
    key: str
    number: int
    product_id: str
    feature_id: str
    current_version: int
    title: str
    preconditions: RichOut
    steps: list[StepOut]
    priority: str
    type: str
    status: str
    automation: str
    automation_ref: str | None = None
    links: list[Link]
    custom: dict[str, Any]
    tags: list[str]
    change_note: str | None = None
    archived_at: UtcDateTime | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class CaseVersionOut(BaseModel):
    case_id: str
    key: str
    version: int
    title: str
    preconditions: RichOut
    steps: list[StepOut]
    priority: str
    type: str
    status: str
    automation: str
    automation_ref: str | None = None
    links: list[Link]
    custom: dict[str, Any]
    tags: list[str]
    change_note: str | None = None
    created_by_actor_id: str
    created_at: UtcDateTime


class CaseVersionSummary(BaseModel):
    version: int
    title: str
    change_note: str | None = None
    created_by_actor_id: str
    created_at: UtcDateTime


class CaseRestore(BaseModel):
    version: int = Field(ge=1)
    change_note: str | None = ChangeNote


class CaseMove(BaseModel):
    feature_id: str


class CaseBulkItem(CaseFields):
    """With `key` (and `expected_version`) it updates that case; without, it creates one (`feature_id` and
    `title` required)."""

    key: str | None = None
    expected_version: int | None = Field(None, ge=1)
    feature_id: str | None = None
    title: str | None = Field(None, min_length=1, max_length=500)


class CaseBulkIn(BaseModel):
    items: list[CaseBulkItem] = Field(min_length=1, max_length=200)


class CaseBulkResult(BaseModel):
    key: str
    id: str
    version: int
    result: Literal["created", "updated", "unchanged"]


class CaseBulkOut(BaseModel):
    items: list[CaseBulkResult]


class TagOut(BaseModel):
    id: str
    name: str
    case_count: int = Field(description="Cases whose current version has the tag, archived ones left out")


class AuditOut(Out):
    id: str
    created_at: datetime
    actor_id: str
    token_id: str | None
    on_behalf_of_user_id: str | None
    via: str
    action: str
    entity_type: str
    entity_id: str
    changes: dict[str, Any] | None
