from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
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


class AuditEvent(TenantMixin, Base):
    """Append-only: an ORM guard and a database trigger refuse UPDATE and DELETE."""

    __tablename__ = "audit_event"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "actor_id"], ["actor.org_id", "actor.id"]),
        ForeignKeyConstraint(["org_id", "token_id"], ["api_token.org_id", "api_token.id"]),
        ForeignKeyConstraint(["org_id", "on_behalf_of_user_id"], ["membership.org_id", "membership.user_id"]),
        CheckConstraint("via IN ('ui', 'api', 'mcp')", name="via"),
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
PLAN_STATUSES = ("active", "archived")


class Product(TenantMixin, UpdatedMixin, Base):
    __tablename__ = "product"
    __table_args__ = tenant_args(UniqueConstraint("org_id", "key"))

    key: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    __test__ = False  # not a pytest class
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
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class PlanEntry(TenantMixin, Base):
    __tablename__ = "plan_entry"
    __table_args__ = tenant_args(
        ForeignKeyConstraint(["org_id", "plan_id"], ["test_plan.org_id", "test_plan.id"]),
        ForeignKeyConstraint(["org_id", "feature_id"], ["feature.org_id", "feature.id"]),
        CheckConstraint(
            "(feature_id IS NOT NULL AND query IS NULL) OR (feature_id IS NULL AND query IS NOT NULL)",
            name="one_target",
        ),
    )

    plan_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    feature_id: Mapped[str | None] = mapped_column(String(26))
    # none_as_null: a feature entry stores SQL NULL here, not JSON null, so `one_target` holds.
    query: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
