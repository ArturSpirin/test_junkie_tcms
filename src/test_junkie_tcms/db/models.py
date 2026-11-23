from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from test_junkie_tcms.db.base import Base, IdMixin, TenantMixin, UpdatedMixin, tenant_args

ROLES = ("viewer", "tester", "editor", "admin", "owner")
_ROLE_CHECK = "role IN ('viewer', 'tester', 'editor', 'admin', 'owner')"


class Org(IdMixin, Base):
    __tablename__ = "org"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class User(IdMixin, Base):
    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UserSession(IdMixin, Base):
    """A cookie login. Global like `user`; it is also the record of login (created_at) and logout."""

    __tablename__ = "session"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("user.id"), nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))


class Membership(TenantMixin, Base):
    __tablename__ = "membership"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "user_id"),
        CheckConstraint(_ROLE_CHECK, name="role"),
    )

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("user.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Removal keeps the row so audit events keep pointing at the member's actor.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Actor(TenantMixin, Base):
    """Who acts in an org: a member (kind='user') or an AI agent owned by a member (kind='agent')."""

    __tablename__ = "actor"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "user_id"),
        ForeignKeyConstraint(["org_id", "user_id"], ["membership.org_id", "membership.user_id"]),
        ForeignKeyConstraint(["org_id", "owner_user_id"], ["membership.org_id", "membership.user_id"]),
        CheckConstraint("kind IN ('user', 'agent')", name="kind"),
        CheckConstraint(
            "(kind = 'user' AND user_id IS NOT NULL AND owner_user_id IS NULL AND role IS NULL)"
            " OR (kind = 'agent' AND user_id IS NULL AND owner_user_id IS NOT NULL AND role IS NOT NULL)",
            name="kind_fields",
        ),
        CheckConstraint(f"role IS NULL OR {_ROLE_CHECK}", name="role"),
    )

    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(26))
    owner_user_id: Mapped[str | None] = mapped_column(String(26))
    role: Mapped[str | None] = mapped_column(String(16))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiToken(TenantMixin, Base):
    __tablename__ = "api_token"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        ForeignKeyConstraint(["org_id", "created_by_actor_id"], ["actor.org_id", "actor.id"]),
    )

    actor_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    created_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    # Product restriction: None means every product in the org.
    product_ids: Mapped[list[str] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invite(TenantMixin, Base):
    """An emailed invite to join an org. Status is computed: revoked > accepted > expired > pending."""

    __tablename__ = "invite"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "invited_by_actor_id"], ["actor.org_id", "actor.id"]),
        ForeignKeyConstraint(["org_id", "accepted_user_id"], ["membership.org_id", "membership.user_id"]),
        CheckConstraint(_ROLE_CHECK, name="role"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Only the SHA-256 of the token; the token itself is shown once, at create.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_user_id: Mapped[str | None] = mapped_column(String(26))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(TenantMixin, Base):
    """Append-only: an ORM guard and a database trigger refuse UPDATE and DELETE."""

    __tablename__ = "audit_event"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        ForeignKeyConstraint(["org_id", "token_id"], ["api_token.org_id", "api_token.id"]),
        ForeignKeyConstraint(["org_id", "on_behalf_of_user_id"], ["membership.org_id", "membership.user_id"]),
        CheckConstraint("via IN ('ui', 'api', 'mcp')", name="via"),
        # An entity's history, e.g. a feature's last editor (T2b).
        Index("ix_audit_event_entity", "org_id", "entity_type", "entity_id"),
    )

    actor_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    token_id: Mapped[str | None] = mapped_column(String(26))
    on_behalf_of_user_id: Mapped[str | None] = mapped_column(String(26))
    via: Mapped[str] = mapped_column(String(8), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(26), nullable=False)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Outbox(TenantMixin, Base):
    """Events for later delivery (webhooks). Mutable, unlike audit_event."""

    __tablename__ = "outbox"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "audit_event_id"], ["audit_event.org_id", "audit_event.id"]),
    )

    audit_event_id: Mapped[str] = mapped_column(String(26), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


# Catalog (T2). Rich fields hold the JSON doc; *_text holds its plain text for search.

RELEASE_STATUSES = ("planned", "in_progress", "released", "cancelled")
PLAN_STATUSES = ("draft", "active", "archived")
# The moves plans_update allows; archived plans are read-only until moved back to active.
PLAN_MOVES = {("draft", "active"), ("active", "archived"), ("archived", "active")}
# A plan entry targets exactly one of a case (T3), a feature or a query.
ONE_TARGET = (
    "(case_id IS NOT NULL AND feature_id IS NULL AND query IS NULL)"
    " OR (case_id IS NULL AND feature_id IS NOT NULL AND query IS NULL)"
    " OR (case_id IS NULL AND feature_id IS NULL AND query IS NOT NULL)"
)


class Product(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "product"
    __table_args__ = tenant_args(UniqueConstraint("org_id", "key"))

    key: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The last case number given out; cases_create bumps it with UPDATE ... RETURNING (T3).
    case_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class Feature(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "feature"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
        ForeignKeyConstraint(["org_id", "parent_id"], ["feature.org_id", "feature.id"]),
        ForeignKeyConstraint(["org_id", "owner_actor_id"], ["actor.org_id", "actor.id"]),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(26))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_actor_id: Mapped[str | None] = mapped_column(String(26))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Release(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "release"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "product_id", "version"),
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
        CheckConstraint(f"status IN {RELEASE_STATUSES}", name="status"),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    target_date: Mapped[date | None] = mapped_column(Date)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    notes_text: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ReleaseFeature(TenantMixin, Base):
    __tablename__ = "release_feature"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "release_id", "feature_id"),
        ForeignKeyConstraint(["org_id", "release_id"], ["release.org_id", "release.id"]),
        ForeignKeyConstraint(["org_id", "feature_id"], ["feature.org_id", "feature.id"]),
    )

    release_id: Mapped[str] = mapped_column(String(26), nullable=False)
    feature_id: Mapped[str] = mapped_column(String(26), nullable=False)


class TestPlan(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "test_plan"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
        ForeignKeyConstraint(["org_id", "release_id"], ["release.org_id", "release.id"]),
        CheckConstraint(f"status IN {PLAN_STATUSES}", name="status"),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    release_id: Mapped[str | None] = mapped_column(String(26))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")


class PlanEntry(TenantMixin, Base):
    __tablename__ = "plan_entry"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "plan_id"], ["test_plan.org_id", "test_plan.id"]),
        ForeignKeyConstraint(["org_id", "feature_id"], ["feature.org_id", "feature.id"]),
        ForeignKeyConstraint(["org_id", "case_id"], ["test_case.org_id", "test_case.id"]),
        CheckConstraint(ONE_TARGET, name="one_target"),
    )

    plan_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    feature_id: Mapped[str | None] = mapped_column(String(26))
    # none_as_null: a feature entry stores SQL NULL here, not JSON null, so `one_target` holds.
    query: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    case_id: Mapped[str | None] = mapped_column(String(26))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# Cases (T3). test_case holds identity and the current version's filter columns; case_version
# rows are never updated or deleted (db/session.py guards it), and every content edit adds one.

CASE_STATUSES = ("draft", "ready", "deprecated")
AUTOMATIONS = ("manual", "automated", "to_automate")
PRIORITIES = ("low", "medium", "high", "critical")
CASE_TYPES = ("functional", "regression", "smoke", "acceptance", "performance", "security", "other")
IDEMPOTENCY_STATES = ("pending", "done")


class TestCase(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "test_case"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "product_id", "number"),
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
        ForeignKeyConstraint(["org_id", "feature_id"], ["feature.org_id", "feature.id"]),
        CheckConstraint(f"status IN {CASE_STATUSES}", name="status"),
        CheckConstraint(f"automation IN {AUTOMATIONS}", name="automation"),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    feature_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Index among the cases of its feature (manual order); ties break by id.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    automation: Mapped[str] = mapped_column(String(16), nullable=False)
    automation_ref: Mapped[str | None] = mapped_column(String(500))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseVersion(TenantMixin, Base):
    __tablename__ = "case_version"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "case_id", "version"),
        ForeignKeyConstraint(["org_id", "case_id"], ["test_case.org_id", "test_case.id"]),
        ForeignKeyConstraint(["org_id", "created_by_actor_id"], ["actor.org_id", "actor.id"]),
        CheckConstraint(f"priority IN {PRIORITIES}", name="priority"),
        CheckConstraint(f"type IN {CASE_TYPES}", name="type"),
        CheckConstraint(f"status IN {CASE_STATUSES}", name="status"),
        CheckConstraint(f"automation IN {AUTOMATIONS}", name="automation"),
    )

    case_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_text: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preconditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    preconditions_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # [{"id", "action": doc, "expected": doc}], in order.
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    steps_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    automation: Mapped[str] = mapped_column(String(16), nullable=False)
    automation_ref: Mapped[str | None] = mapped_column(String(500))
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    custom: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String(500))
    created_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)


class Tag(TenantMixin, Base):
    __tablename__ = "tag"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "product_id", "name"),
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class CaseVersionTag(TenantMixin, Base):
    __tablename__ = "case_version_tag"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "case_version_id", "tag_id"),
        ForeignKeyConstraint(["org_id", "case_version_id"], ["case_version.org_id", "case_version.id"]),
        ForeignKeyConstraint(["org_id", "tag_id"], ["tag.org_id", "tag.id"]),
    )

    case_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    tag_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)


class IdempotencyRecord(TenantMixin, Base):
    """One Idempotency-Key per (org, actor): pending until the recorder stores the first response."""

    __tablename__ = "idempotency_record"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "actor_id", "key"),
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        CheckConstraint(f"state IN {IDEMPOTENCY_STATES}", name="state"),
    )

    actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSON(none_as_null=True))
    response_headers: Mapped[dict[str, str] | None] = mapped_column(JSON(none_as_null=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


# Consumers: a machine running the test_junkie daemon, paired by device code.

PAIRING_STATUSES = ("pending", "approved", "claimed")


class Consumer(TenantMixin, Base):
    """Acts through its own agent actor; its token is minted when the paired consumer claims it."""

    __tablename__ = "consumer"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        ForeignKeyConstraint(["org_id", "token_id"], ["api_token.org_id", "api_token.id"]),
        ForeignKeyConstraint(["org_id", "approved_by_actor_id"], ["actor.org_id", "actor.id"]),
    )

    # User-given; never the machine's hostname. Unique among the org's consumers that aren't revoked.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(26), nullable=False, unique=True)
    token_id: Mapped[str | None] = mapped_column(String(26))
    approved_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The job the consumer holds, set and cleared by the server (T8). A plain id, no FK: job points here.
    busy_job_id: Mapped[str | None] = mapped_column(String(26))
    tj_version: Mapped[str | None] = mapped_column(String(64))
    python: Mapped[str | None] = mapped_column(String(64))
    os: Mapped[str | None] = mapped_column(String(200))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsumerProduct(TenantMixin, Base):
    __tablename__ = "consumer_product"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "consumer_id", "product_id"),
        ForeignKeyConstraint(["org_id", "consumer_id"], ["consumer.org_id", "consumer.id"]),
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
    )

    consumer_id: Mapped[str] = mapped_column(String(26), nullable=False)
    product_id: Mapped[str] = mapped_column(String(26), nullable=False)


class PairingRequest(IdMixin, Base):
    """RFC 8628 device code. Pre-tenant: org_id and consumer_id stay NULL until an admin approves it."""

    __tablename__ = "pairing_request"
    __table_args__ = (
        UniqueConstraint("org_id", "id"),
        ForeignKeyConstraint(["org_id", "consumer_id"], ["consumer.org_id", "consumer.id"]),
        CheckConstraint(f"status IN {PAIRING_STATUSES}", name="status"),
    )

    org_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("org.id"), index=True)
    device_code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_code: Mapped[str] = mapped_column(String(9), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumer_id: Mapped[str | None] = mapped_column(String(26))
    client_ip: Mapped[str | None] = mapped_column(String(64))


class ConsumerHeartbeat(TenantMixin, Base):
    """One row per heartbeat; rows older than 24 h are dropped on the next heartbeat."""

    __tablename__ = "consumer_heartbeat"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "consumer_id"], ["consumer.org_id", "consumer.id"]),
        Index("ix_consumer_heartbeat_consumer_id_at", "consumer_id", "at"),
    )

    consumer_id: Mapped[str] = mapped_column(String(26), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    busy_job_id: Mapped[str | None] = mapped_column(String(26))


class ConsumerInventory(TenantMixin, UpdatedMixin, Base):
    """The tests one consumer project can run, stored by hash: an unchanged hash writes nothing."""

    __tablename__ = "consumer_inventory"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "consumer_id", "project"),
        ForeignKeyConstraint(["org_id", "consumer_id"], ["consumer.org_id", "consumer.id"]),
    )

    consumer_id: Mapped[str] = mapped_column(String(26), nullable=False)
    project: Mapped[str] = mapped_column(String(200), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    roster: Mapped[Any] = mapped_column(JSON, nullable=False)
    test_count: Mapped[int] = mapped_column(Integer, nullable=False)


# Execution (T4). A cycle_case pins the case_version it runs; result and result_attachment rows
# are never updated or deleted (db/session.py guards it), and a retest is the next attempt.

CYCLE_CASE_STATUSES = ("untested", "success", "fail", "error", "ignore", "skip", "cancel")
RESULT_STATUSES = CYCLE_CASE_STATUSES[1:]
STEP_STATUSES = ("untested", "success", "fail", "error", "skip")
CYCLE_STATUSES = ("open", "closed")
BATCH_MODES = ("features", "plans")
RESULT_VIAS = ("ui", "api", "mcp", "consumer")
CYCLE_MODES = ("manual", "automated", "both")
RUNNERS = ("person", "consumer")
JOB_STATUSES = ("queued", "claimed", "running", "done", "failed", "cancelled", "rejected")


class CycleBatch(TenantMixin, Base):
    __tablename__ = "cycle_batch"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
        ForeignKeyConstraint(["org_id", "release_id"], ["release.org_id", "release.id"]),
        ForeignKeyConstraint(["org_id", "created_by_actor_id"], ["actor.org_id", "actor.id"]),
        CheckConstraint(f"mode IN {BATCH_MODES}", name="mode"),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    release_id: Mapped[str] = mapped_column(String(26), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    environment: Mapped[str | None] = mapped_column(String(64))
    created_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)


class Cycle(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "cycle"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
        ForeignKeyConstraint(["org_id", "release_id"], ["release.org_id", "release.id"]),
        ForeignKeyConstraint(["org_id", "plan_id"], ["test_plan.org_id", "test_plan.id"]),
        ForeignKeyConstraint(["org_id", "batch_id"], ["cycle_batch.org_id", "cycle_batch.id"]),
        ForeignKeyConstraint(["org_id", "feature_id"], ["feature.org_id", "feature.id"]),
        ForeignKeyConstraint(["org_id", "default_assignee_actor_id"], ["actor.org_id", "actor.id"]),
        ForeignKeyConstraint(["org_id", "created_by_actor_id"], ["actor.org_id", "actor.id"]),
        CheckConstraint(f"status IN {CYCLE_STATUSES}", name="status"),
        CheckConstraint(f"mode IN {CYCLE_MODES}", name="mode"),
        Index("ix_cycle_org_id_batch_id", "org_id", "batch_id"),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    release_id: Mapped[str | None] = mapped_column(String(26))
    plan_id: Mapped[str | None] = mapped_column(String(26))
    batch_id: Mapped[str | None] = mapped_column(String(26))
    # Set on a bulk cycle made per affected feature.
    feature_id: Mapped[str | None] = mapped_column(String(26))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    environment: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # automated and both send cases with a known automation_ref to consumers as jobs (T8).
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="manual", server_default="manual")
    default_assignee_actor_id: Mapped[str | None] = mapped_column(String(26))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)


class CycleCase(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "cycle_case"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "cycle_id", "case_id"),
        ForeignKeyConstraint(["org_id", "cycle_id"], ["cycle.org_id", "cycle.id"]),
        ForeignKeyConstraint(["org_id", "case_id"], ["test_case.org_id", "test_case.id"]),
        ForeignKeyConstraint(["org_id", "case_version_id"], ["case_version.org_id", "case_version.id"]),
        ForeignKeyConstraint(["org_id", "assignee_actor_id"], ["actor.org_id", "actor.id"]),
        ForeignKeyConstraint(["org_id", "consumer_id"], ["consumer.org_id", "consumer.id"]),
        ForeignKeyConstraint(["org_id", "job_id"], ["job.org_id", "job.id"]),
        CheckConstraint(f"status IN {CYCLE_CASE_STATUSES}", name="status"),
        CheckConstraint(f"runner IN {RUNNERS}", name="runner"),
    )

    cycle_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    # The pin: the row of the version this cycle runs, and its number for display.
    case_version_id: Mapped[str] = mapped_column(String(26), nullable=False)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_actor_id: Mapped[str | None] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="untested")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runner: Mapped[str] = mapped_column(String(8), nullable=False, default="person", server_default="person")
    consumer_id: Mapped[str | None] = mapped_column(String(26))
    job_id: Mapped[str | None] = mapped_column(String(26), index=True)


class Job(TenantMixin, UpdatedMixin, Base):
    """One consumer's share of a cycle for one project: the refs it runs."""

    __tablename__ = "job"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "cycle_id"], ["cycle.org_id", "cycle.id"]),
        ForeignKeyConstraint(["org_id", "consumer_id"], ["consumer.org_id", "consumer.id"]),
        CheckConstraint(f"status IN {JOB_STATUSES}", name="status"),
        Index("ix_job_consumer_id_status", "consumer_id", "status"),
    )

    cycle_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    consumer_id: Mapped[str] = mapped_column(String(26), nullable=False)
    project: Mapped[str] = mapped_column(String(200), nullable=False)
    refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_beat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cancelled while claimed: the id goes in the consumer's next heartbeat reply, then this is set.
    cancel_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Result(TenantMixin, Base):
    __tablename__ = "result"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "cycle_case_id", "attempt"),
        ForeignKeyConstraint(["org_id", "cycle_case_id"], ["cycle_case.org_id", "cycle_case.id"]),
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        CheckConstraint(f"status IN {RESULT_STATUSES}", name="status"),
        CheckConstraint(f"via IN {RESULT_VIAS}", name="via"),
    )

    cycle_case_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    via: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # [{"step_id", "status", "actual": doc, "attachment_ids": [...]}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    attachment_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    # [{"url", "key"?}]
    defects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Attachment(TenantMixin, Base):
    """A stored file, deduplicated by content within a product; the bytes live in Storage."""

    __tablename__ = "attachment"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "product_id", "sha256", "filename"),
        ForeignKeyConstraint(["org_id", "product_id"], ["product.org_id", "product.id"]),
        ForeignKeyConstraint(["org_id", "created_by_actor_id"], ["actor.org_id", "actor.id"]),
    )

    product_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(127), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)


class ResultAttachment(TenantMixin, Base):
    __tablename__ = "result_attachment"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "result_id", "attachment_id"),
        ForeignKeyConstraint(["org_id", "result_id"], ["result.org_id", "result.id"]),
        ForeignKeyConstraint(["org_id", "attachment_id"], ["attachment.org_id", "attachment.id"]),
    )

    result_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    attachment_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)


class McpToolStat(TenantMixin, Base):
    """Calls, errors and response sizes per org, tool, actor and UTC hour."""

    __tablename__ = "mcp_tool_stat"
    __table_args__ = tenant_args(
        UniqueConstraint("org_id", "tool", "actor_id", "hour"),
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        Index("ix_mcp_tool_stat_org_id_hour", "org_id", "hour"),
    )

    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, nullable=False)
    resp_bytes_sum: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 24 counts; bucket i holds sizes in [2^i, 2^(i+1)) bytes (0 also holds 0-1 B, 23 everything above)
    resp_bytes_hist: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    # the errors by HTTP status, e.g. {"409": 3, "422": 1}; its counts add up to `errors`
    error_codes: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))


class McpToolCall(TenantMixin, Base):
    """One MCP call: when, which tool, who, its status and latency. Kept 7 days per org."""

    __tablename__ = "mcp_tool_call"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        Index("ix_mcp_tool_call_org_id_at", "org_id", "at"),
        Index("ix_mcp_tool_call_org_id_tool_at", "org_id", "tool", "at"),
    )

    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    ms: Mapped[int] = mapped_column(Integer, nullable=False)
    resp_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


MCP_SERVER_EVENT_KINDS = ("server_started", "tools_changed")


class McpServerEvent(IdMixin, Base):
    """A start of the MCP server, or a change in its tool list between starts. Server-wide, not per org."""

    __tablename__ = "mcp_server_event"
    __table_args__ = (CheckConstraint("kind IN ('server_started', 'tools_changed')", name="kind"),)

    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    tool_list_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # name -> sha256 of that tool's definition, so the next start can name what changed
    tool_hashes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    added: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    removed: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    changed: Mapped[list[str]] = mapped_column(JSON, nullable=False)
