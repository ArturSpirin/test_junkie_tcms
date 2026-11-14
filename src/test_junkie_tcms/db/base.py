from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from ulid import ULID

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Tables that are global by design, with the reason. Every other table is a tenant table.
GLOBAL_TABLES = {
    "org": "the tenant itself",
    "user": "a person's account spans orgs; per-org rights live in membership",
    "session": "a login spans orgs; it holds no org data",
    "alembic_version": "migration bookkeeping",
}

# Tenant tables whose rows start with no org: org_id may be NULL until the row is bound to one.
PRE_TENANT_TABLES = {
    "pairing_request": "a consumer asks to pair before anyone picks the org; approval sets org_id",
}


def new_id() -> str:
    return str(ULID())


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; every stored time is UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class IdMixin:
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UpdatedMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


def tenant_args(*extra):
    """`__table_args__` for a tenant table: UNIQUE(org_id, id) so children can point at (org_id, id)."""
    return (UniqueConstraint("org_id", "id"), *extra)


class TenantMixin(IdMixin):
    """Every tenant table: a non-null org_id and UNIQUE(org_id, id). Child FKs are composite."""

    org_id: Mapped[str] = mapped_column(String(26), ForeignKey("org.id"), nullable=False, index=True)

    @declared_attr.directive
    def __table_args__(cls):
        return tenant_args()
