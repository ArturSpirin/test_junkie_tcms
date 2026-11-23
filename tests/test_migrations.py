"""Migrations build the models' schema, and the database itself keeps audit_event append-only."""

import json
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
from tests.execution_seed import cycle_cases, edit_steps, make_case, make_cycle, record, run_seed


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

    @test()
    def test_migrations_form_one_numbered_chain(self):
        # Two branches can each add "0011" off 0010; Alembic then keeps only one file per id, so the
        # duplicate is lost silently. Each file's prefix is its id, and each revises the number before it.
        script = ScriptDirectory.from_config(alembic_config("sqlite://"))
        revisions = list(script.walk_revisions())
        prefixes = sorted(Path(revision.path).name.split("_", 1)[0] for revision in revisions)
        files = sorted(path.name.split("_", 1)[0] for path in Path(script.versions).glob("[0-9]*.py"))
        assert files == prefixes, (files, prefixes)
        for revision in revisions:
            assert Path(revision.path).name.startswith(f"{revision.revision}_"), revision.path
            number = int(revision.revision)
            expected = None if number == 1 else f"{number - 1:04d}"
            assert revision.down_revision == expected, (revision.revision, revision.down_revision)


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
    def test_0017_gives_existing_versions_an_empty_description(self, suite_parameter):
        s = seed(self.env.owner)
        make_case(self.env.owner, s["product"]["id"], s["child"]["id"], "Card")
        database_url = self.env.database_url
        command.downgrade(alembic_config(database_url), "0016")
        migrate.upgrade(database_url)
        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                [(doc, plain)] = conn.execute(text("SELECT description, description_text FROM case_version"))
            assert (json.loads(doc) if isinstance(doc, str) else doc, plain) == (
                {"type": "doc", "content": []},
                "",
            )
        finally:
            engine.dispose()

    @test()
    def test_0015_backfills_result_case_version_from_the_pin(self, suite_parameter):
        owner = self.env.owner
        s = run_seed(owner)
        ok(record(owner, s["cycle_case"]["id"], status="fail"), 201)
        ok(record(owner, s["cycle_case"]["id"], status="success"), 201)
        edit_steps(owner, s["case"])
        later = make_cycle(owner, s["product"]["id"], case_ids=[s["case"]["id"]])
        [cc2] = cycle_cases(owner, later["id"])
        ok(record(owner, cc2["id"], status="success"), 201)

        database_url = self.env.database_url
        command.downgrade(alembic_config(database_url), "0014")
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

    @test()
    def test_0014_keeps_pending_pairings_and_drops_denied_on_downgrade(self, suite_parameter):
        owner, anon = self.env.owner, self.env.client()
        kept = ok(anon.post("/api/v1/pair", json={"os": "Linux"}), 201)["user_code"]
        denied = ok(anon.post("/api/v1/pair"), 201)["user_code"]
        assert owner.post("/api/v1/orgs/acme/pair/deny", json={"user_code": denied}).status_code == 204
        database_url = self.env.database_url
        engine = create_engine(database_url)
        rows = "SELECT user_code, status FROM pairing_request ORDER BY user_code"
        try:
            command.downgrade(alembic_config(database_url), "0013")
            with engine.connect() as conn:
                assert "machine" not in {c["name"] for c in inspect(conn).get_columns("pairing_request")}
                assert "paused_at" not in {c["name"] for c in inspect(conn).get_columns("consumer")}
                assert "reason" not in {c["name"] for c in inspect(conn).get_columns("job")}
                assert list(conn.execute(text(rows))) == [(kept, "pending")]
            migrate.upgrade(database_url)
            with engine.connect() as conn:
                assert list(conn.execute(text(rows))) == [(kept, "pending")]
                assert conn.scalar(text("SELECT machine FROM pairing_request")) is None
        finally:
            engine.dispose()

    @test()
    def test_0016_drops_activity_and_provenance_on_downgrade_and_adds_them_back(self, suite_parameter):
        database_url = self.env.settings.database_url
        engine = create_engine(database_url)

        def columns(conn, table):
            return {c["name"] for c in inspect(conn).get_columns(table)}

        try:
            command.downgrade(alembic_config(database_url), "0015")
            with engine.connect() as conn:
                assert not {"last_active_at", "description"} & columns(conn, "actor")
                assert not {"via", "token_id", "on_behalf_of_user_id"} & columns(conn, "case_version")
            migrate.upgrade(database_url)
            with engine.connect() as conn:
                assert {"last_active_at", "description"} <= columns(conn, "actor")
                assert {"via", "token_id", "on_behalf_of_user_id"} <= columns(conn, "case_version")
        finally:
            engine.dispose()

    @test()
    def test_0018_gives_agents_valid_names_unique_per_org_and_drops_request_columns_on_downgrade(
        self, suite_parameter
    ):
        owner = self.env.owner
        globex = self.env.client()
        support.login(globex, "other@example.com")
        kept = ok(owner.post("/api/v1/orgs/acme/agents", json={"name": "ci-bot", "role": "viewer"}), 201)
        other = ok(globex.post("/api/v1/orgs/globex/agents", json={"name": "ci-bot", "role": "viewer"}), 201)
        database_url = self.env.database_url
        engine = create_engine(database_url)

        def columns(conn):
            return {c["name"] for c in inspect(conn).get_columns("audit_event")}

        try:
            command.downgrade(alembic_config(database_url), "0017")
            with engine.begin() as conn:
                assert not {"request_id", "tool"} & columns(conn)
                org_id, user_id, actor_id = conn.execute(
                    text(
                        "SELECT a.org_id, a.user_id, a.id FROM actor a JOIN org o ON o.id = a.org_id"
                        " WHERE o.slug = 'acme' AND a.kind = 'user'"
                    )
                ).one()
                # Older than ci-bot, yet ci-bot already meets the rule, so it keeps its name.
                for id_, name, created in [
                    ("A1", "CI Bot", "2026-01-01"),
                    ("A2", "ci  bot!", "2026-01-02"),
                    ("A3", "__", "2026-01-03"),
                    ("A4", "Build Box", "2026-01-04"),
                ]:
                    conn.execute(
                        text(
                            "INSERT INTO actor (id, org_id, kind, name, owner_user_id, role, created_at)"
                            " VALUES (:id, :org, 'agent', :name, :user, 'viewer', :created)"
                        ),
                        {"id": id_, "org": org_id, "name": name, "user": user_id, "created": created},
                    )
                conn.execute(  # A4 is a consumer's actor: consumer names have their own rule
                    text(
                        "INSERT INTO consumer (id, org_id, name, actor_id, approved_by_actor_id, created_at)"
                        " VALUES ('C1', :org, 'Build Box', 'A4', :actor, '2026-01-04')"
                    ),
                    {"org": org_id, "actor": actor_id},
                )
            migrate.upgrade(database_url)
            with engine.connect() as conn:
                assert {"request_id", "tool"} <= columns(conn)
                names = dict(conn.execute(text("SELECT id, name FROM actor WHERE kind = 'agent'")).all())
            assert names == {
                kept["id"]: "ci-bot",
                "A1": "ci-bot-2",
                "A2": "ci-bot-3",
                "A3": "agent",
                "A4": "Build Box",
                other["id"]: "ci-bot",  # unique per org: globex keeps its own ci-bot
            }
            command.downgrade(alembic_config(database_url), "0017")
            with engine.connect() as conn:
                assert not {"request_id", "tool"} & columns(conn)
                assert conn.scalar(text("SELECT name FROM actor WHERE id = 'A1'")) == "ci-bot-2"  # one-way
            migrate.upgrade(database_url)
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
