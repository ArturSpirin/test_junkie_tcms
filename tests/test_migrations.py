"""Migrations build the models' schema, and the database itself keeps audit_event append-only."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError

from test_junkie_tcms.db.base import Base
from test_junkie_tcms.db.migrate import alembic_config
from test_junkie_tcms.db.models import AuditEvent
from test_junkie_tcms.db.session import AuditAppendOnlyError, make_engine, make_sessionmaker


def test_migrations_match_models(settings):
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as conn:
            assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    finally:
        engine.dispose()


def test_migrations_have_one_head():
    # Branches that each add a revision off the same parent give two heads; re-chain before merging.
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    assert len(script.get_heads()) == 1, script.get_heads()


@pytest.fixture
def one_event(owner, settings):
    response = owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
    assert response.status_code == 200, response.text
    engine = make_engine(settings.database_url)
    yield engine
    engine.dispose()


def _count(engine) -> int:
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(AuditEvent))


@pytest.mark.parametrize("statement", ["UPDATE audit_event SET action = 'x'", "DELETE FROM audit_event"])
def test_raw_sql_cannot_change_audit_event(one_event, statement):
    with pytest.raises(DBAPIError, match="append-only"):
        with one_event.begin() as conn:
            conn.execute(text(statement))
    assert _count(one_event) == 1


def test_orm_cannot_change_audit_event(one_event):
    with make_sessionmaker(one_event)() as db:
        event = db.scalar(select(AuditEvent))
        event.action = "x"
        with pytest.raises(AuditAppendOnlyError):
            db.flush()
        db.rollback()
        db.delete(db.scalar(select(AuditEvent)))
        with pytest.raises(AuditAppendOnlyError):
            db.flush()


def test_postgres_retention_switch_allows_delete(one_event):
    if one_event.dialect.name != "postgresql":
        pytest.skip("the retention switch is a Postgres session setting")
    with one_event.begin() as conn:
        conn.execute(text("SET LOCAL tcms.retention = 'on'"))
        conn.execute(text("DELETE FROM outbox"))
        conn.execute(text("DELETE FROM audit_event"))
    assert _count(one_event) == 0
