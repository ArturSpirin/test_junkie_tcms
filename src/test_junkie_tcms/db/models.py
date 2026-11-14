from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from test_junkie_tcms.db.base import Base, IdMixin, TenantMixin, tenant_args

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
    # Product restriction; applied from T2. T1 refuses a non-null value.
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
