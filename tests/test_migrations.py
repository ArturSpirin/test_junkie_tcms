"""Migrations build the models' schema, and the database itself keeps audit_event append-only."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test
from test_junkie.shortcuts import skip

from test_junkie_tcms.db import migrate
from test_junkie_tcms.db.base import Base
from test_junkie_tcms.db.migrate import alembic_config
from test_junkie_tcms.db.models import AuditEvent
from test_junkie_tcms.db.session import AuditAppendOnlyError, make_engine, make_sessionmaker
from tests import support
from tests.catalog_seed import ok
from tests.execution_seed import cycle_cases, edit_steps, make_cycle, record, run_seed


def _count(engine) -> int:
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(AuditEvent))


@Suite()
class MigrationScripts:
    @test()
    def test_migrations_have_one_head(self):
        # Branches that each add a revision off the same parent give two heads; re-chain before merging.
        script = ScriptDirectory.from_config(alembic_config("sqlite://"))
        assert len(script.get_heads()) == 1, script.get_heads()


@Suite(parameters=support.DATABASES)
class Migrations:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def one_event(self):
        """The old one_event fixture: one audit event, and an engine on the database (dispose it after)."""
        owner = self.env.owner
        settings = self.env.settings
        response = owner.patch("/api/v1/orgs/acme", json={"name": "Acme Inc"})
        assert response.status_code == 200, response.text
        return make_engine(settings.database_url)

    @test()
    def test_migrations_match_models(self, suite_parameter):
        settings = self.env.settings
        engine = create_engine(settings.database_url)
        try:
            with engine.connect() as conn:
                assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        finally:
            engine.dispose()

    @test()
    def test_0006_keeps_existing_plans_active(self, suite_parameter):
        database_url = self.env.database_url
        migrate.upgrade(database_url, "0005")
        engine = create_engine(database_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO org (id, slug, name, created_at) VALUES ('O1', 'o', 'O', '2026-11-14')")
                )
                conn.execute(
                    text(
                        "INSERT INTO product (id, org_id, key, name, description, description_text,"
                        " created_at, updated_at)"
                        " VALUES ('P1', 'O1', 'PAY', 'Pay', '{}', '', '2026-11-14', '2026-11-14')"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO test_plan (id, org_id, product_id, name, description, description_text,"
                        " status, created_at, updated_at)"
                        " VALUES ('T1', 'O1', 'P1', 'Smoke', '{}', '', 'active', '2026-11-14', '2026-11-14')"
                    )
                )
            migrate.upgrade(database_url)
            with engine.connect() as conn:
                assert conn.scalar(text("SELECT status FROM test_plan WHERE id = 'T1'")) == "active"
        finally:
            engine.dispose()

    @test()
    def test_0011_backfills_result_case_version_from_the_pin(self, suite_parameter):
        owner = self.env.owner
        s = run_seed(owner)
        ok(record(owner, s["cycle_case"]["id"], status="fail"), 201)
        ok(record(owner, s["cycle_case"]["id"], status="success"), 201)
        edit_steps(owner, s["case"])
        later = make_cycle(owner, s["product"]["id"], case_ids=[s["case"]["id"]])
        [cc2] = cycle_cases(owner, later["id"])
        ok(record(owner, cc2["id"], status="success"), 201)

        database_url = self.env.database_url
        command.downgrade(alembic_config(database_url), "0010")
        migrate.upgrade(database_url)
        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT r.case_version, cc.case_version FROM result r JOIN cycle_case cc"
                        " ON cc.org_id = r.org_id AND cc.id = r.cycle_case_id ORDER BY r.case_version"
                    )
                ).all()
        finally:
            engine.dispose()
        assert [tuple(r) for r in rows] == [(1, 1), (1, 1), (2, 2)]

    @test(parameters=["UPDATE audit_event SET action = 'x'", "DELETE FROM audit_event"])
    def test_raw_sql_cannot_change_audit_event(self, parameter, suite_parameter):
        statement = parameter
        one_event = self.one_event()
        try:
            with support.raises(DBAPIError, match="append-only"):
                with one_event.begin() as conn:
                    conn.execute(text(statement))
            assert _count(one_event) == 1
        finally:
            one_event.dispose()

    @test()
    def test_orm_cannot_change_audit_event(self, suite_parameter):
        one_event = self.one_event()
        try:
            with make_sessionmaker(one_event)() as db:
                event = db.scalar(select(AuditEvent))
                event.action = "x"
                with support.raises(AuditAppendOnlyError):
                    db.flush()
                db.rollback()
                db.delete(db.scalar(select(AuditEvent)))
                with support.raises(AuditAppendOnlyError):
                    db.flush()
        finally:
            one_event.dispose()

    @test()
    def test_postgres_retention_switch_allows_delete(self, suite_parameter):
        one_event = self.one_event()
        try:
            if one_event.dialect.name != "postgresql":
                skip("the retention switch is a Postgres session setting")
            with one_event.begin() as conn:
                conn.execute(text("SET LOCAL tcms.retention = 'on'"))
                conn.execute(text("DELETE FROM outbox"))
                conn.execute(text("DELETE FROM audit_event"))
            assert _count(one_event) == 0
        finally:
            one_event.dispose()
