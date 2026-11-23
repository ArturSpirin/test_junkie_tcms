"""Every Postgres connection reads times in UTC, whatever the server's time zone (db/base.py's contract)."""

from datetime import timedelta

from sqlalchemy import create_engine, text
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test
from test_junkie.shortcuts import skip

from test_junkie_tcms.db.session import make_engine
from tests import support

INSTANT = text("SELECT TIMESTAMPTZ '2026-11-23 12:00:00+00'")


@Suite(parameters=support.DATABASES)
class DbSessionTimezone:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    @test()
    def test_postgres_reads_times_in_utc_on_a_non_utc_database(self, suite_parameter):
        if suite_parameter != "postgres":
            skip("the session time zone is a Postgres setting")
        database_url = self.env.database_url
        plain = create_engine(database_url)
        engine = make_engine(database_url)
        try:
            # The test database really is non-UTC: a plain engine reads the instant in Pacific time.
            with plain.connect() as conn:
                assert conn.scalar(text("SHOW TimeZone")) == support.PG_TEST_TIMEZONE
                assert conn.scalar(INSTANT).utcoffset() != timedelta(0)
            with engine.connect() as conn:
                first = conn.connection.dbapi_connection
                assert conn.scalar(text("SHOW TimeZone")) == "UTC"
                assert conn.scalar(INSTANT).utcoffset() == timedelta(0)
                assert conn.scalar(text("SELECT now()")).utcoffset() == timedelta(0)
                conn.rollback()
            # The same pooled connection, checked out again after a ROLLBACK, keeps UTC.
            with engine.connect() as conn:
                assert conn.connection.dbapi_connection is first
                assert conn.scalar(text("SHOW TimeZone")) == "UTC"
                assert conn.scalar(INSTANT).utcoffset() == timedelta(0)
        finally:
            plain.dispose()
            engine.dispose()
