"""Migrations build the models' schema, and the database itself keeps audit_event append-only."""

import shutil
import tempfile
import warnings
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test
from test_junkie.shortcuts import skip

from test_junkie_tcms.db import migrate
from test_junkie_tcms.db.base import Base
from test_junkie_tcms.db.migrate import alembic_config
from test_junkie_tcms.db.models import AuditEvent
from test_junkie_tcms.db.session import AuditAppendOnlyError, make_engine, make_sessionmaker
from tests import support
from tests.catalog_seed import ok, seed, url


def _count(engine) -> int:
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(AuditEvent))


def _chain_problems(location) -> list[str]:
    """Every way the migrations at location fail to be one chain 0001…N, each file named for its revision."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        script = ScriptDirectory(str(location))
        revisions = list(script.walk_revisions())
    # Alembic keeps one file per revision id and only warns, so a duplicate shows as a lost file.
    problems = [str(w.message) for w in caught if "more than once" in str(w.message)]
    files = sorted(path.name for path in Path(script.versions).glob("[0-9][0-9][0-9][0-9]_*.py"))
    if len(files) != len(revisions):
        problems.append(f"{len(files)} files but {len(revisions)} revisions")
    heads = script.get_heads()
    if len(heads) != 1:
        problems.append(f"heads {sorted(heads)}, want one")
    for revision in revisions:
        name = Path(revision.path).name
        if not name.startswith(f"{revision.revision}_"):
            problems.append(f"{name} has revision {revision.revision}")
        number = int(revision.revision)
        expected = None if number == 1 else f"{number - 1:04d}"
        if revision.down_revision != expected:
            problems.append(f"{revision.revision} revises {revision.down_revision}, want {expected}")
    numbers = sorted(int(revision.revision) for revision in revisions)
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"numbers {numbers} have a gap")
    return problems


# Each bad case adds a file made from 0012 to a copy of migrations/: file, revision, down_revision, problem.
_BAD_CHAINS = {
    "duplicate_id": ("0012_other_branch.py", "0012", "0011", "present more than once"),
    "two_heads": ("0013_other_branch.py", "0013", "0011", "heads ['0012', '0013']"),
    "prefix_mismatch": ("0013_other_branch.py", "0014", "0012", "0013_other_branch.py has revision 0014"),
    "gap": ("0014_other_branch.py", "0014", "0012", "have a gap"),
}


@Suite()
class MigrationScripts:
    @test()
    def test_migrations_have_one_head(self):
        # Branches that each add a revision off the same parent give two heads; re-chain before merging.
        script = ScriptDirectory.from_config(alembic_config("sqlite://"))
        assert len(script.get_heads()) == 1, script.get_heads()

    @test()
    def test_migrations_form_one_numbered_chain(self):
        # Parallel branches each take "the next" number off the staging they started from; merging
        # origin/staging into a branch that clashes fails here, before review.
        script = ScriptDirectory.from_config(alembic_config("sqlite://"))
        assert _chain_problems(script.dir) == []

    @test(parameters=list(_BAD_CHAINS))
    def test_chain_check_catches(self, parameter):
        name, revision, down_revision, problem = _BAD_CHAINS[parameter]
        real = Path(ScriptDirectory.from_config(alembic_config("sqlite://")).dir)
        source = (real / "versions" / "0012_case_position.py").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "migrations"
            shutil.copytree(real, copy, ignore=shutil.ignore_patterns("__pycache__"))
            bad = source.replace('revision = "0012"', f'revision = "{revision}"', 1)
            bad = bad.replace('down_revision = "0011"', f'down_revision = "{down_revision}"', 1)
            (copy / "versions" / name).write_text(bad, encoding="utf-8")
            problems = _chain_problems(copy)
        assert any(problem in found for found in problems), problems


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
    def test_0012_numbers_positions_in_key_order_and_downgrades(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, card, parent = s["product"]["id"], s["child"]["id"], s["parent"]["id"]
        for feature in (card, parent, card, card, parent):  # PAY-1 to PAY-5
            ok(owner.post(url(f"/products/{p}/cases"), json={"feature_id": feature, "title": "t"}), 201)
        database_url = self.env.database_url
        engine = create_engine(database_url)
        rows = "SELECT number, feature_id, position, updated_at FROM test_case ORDER BY number"
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE test_case SET position = 7"))
                before = [(n, f, u) for n, f, _, u in conn.execute(text(rows))]
            command.downgrade(alembic_config(database_url), "0011")
            with engine.connect() as conn:
                assert "position" not in {c["name"] for c in inspect(conn).get_columns("test_case")}
            migrate.upgrade(database_url)
            with engine.connect() as conn:
                after = list(conn.execute(text(rows)))
            assert [(n, f, u) for n, f, _, u in after] == before  # updated_at is left as it was
            assert [(n, pos) for n, _, pos, _ in after] == [(1, 0), (2, 0), (3, 1), (4, 2), (5, 1)]
        finally:
            engine.dispose()

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
