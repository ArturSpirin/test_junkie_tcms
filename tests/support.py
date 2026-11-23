"""Test helpers for the Test Junkie suites.

Every database suite runs on SQLite, and on Postgres too when TJ_TCMS_TEST_POSTGRES_URL is set. A suite takes
``parameters=DATABASES`` and opens a fresh ``Env`` per test, so each test gets its own database, like the old
function-scoped fixtures.
"""

import os
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from test_junkie_tcms.app import create_app
from test_junkie_tcms.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from test_junkie_tcms.cli import create_admin
from test_junkie_tcms.db import migrate
from test_junkie_tcms.settings import Settings

POSTGRES_URL = os.environ.get("TJ_TCMS_TEST_POSTGRES_URL")
PG_TEST_TIMEZONE = "America/Los_Angeles"
OWNER_EMAIL = "owner@example.com"
PASSWORD = "correct horse battery"

DATABASES = ["sqlite"] + (["postgres"] if POSTGRES_URL else [])

_OPEN: set["Env"] = set()


class Env:
    """One test's world: a temp dir, a database, settings, the app and its clients, each made on first use.

    ``close()`` undoes patches, closes clients, disposes the engine, drops a Postgres database and removes the
    temp dir. It is safe to call twice. Every Env registers itself before it creates anything, so
    ``close_all()`` (each suite's ``afterClass``) also closes one whose ``afterTest`` never ran.
    """

    def __init__(self, kind: str):
        if kind not in ("sqlite", "postgres"):
            # Test Junkie passes the suite parameter to hooks only for tests that declare `suite_parameter`.
            raise ValueError(f"unknown database {kind!r}: does the test declare suite_parameter?")
        self.kind = kind
        self.tmp = Path(tempfile.mkdtemp(prefix="tcms_test_"))
        self._clients: list[TestClient] = []
        self._patches: list = []
        self._pg_admin = None
        self._pg_name = None
        self._database_url = None
        self._settings = None
        self._app = None
        self._owner = None
        self._closed = False
        _OPEN.add(self)

    @property
    def database_url(self) -> str:
        """A fresh, empty database (not migrated)."""
        if self._database_url is None:
            if self.kind == "sqlite":
                self._database_url = f"sqlite:///{(self.tmp / 'tcms.db').as_posix()}"
            else:
                admin_url = make_url(POSTGRES_URL)
                self._pg_admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
                self._pg_name = f"tcms_test_{uuid.uuid4().hex[:12]}"
                with self._pg_admin.connect() as conn:
                    conn.execute(text(f'CREATE DATABASE "{self._pg_name}"'))
                    # A non-UTC database, so a time read back in the server's zone fails here, not only in
                    # prod (CI's Postgres runs in UTC). make_engine must still read every time in UTC.
                    conn.execute(
                        text(f"ALTER DATABASE \"{self._pg_name}\" SET timezone TO '{PG_TEST_TIMEZONE}'")
                    )
                self._database_url = admin_url.set(database=self._pg_name).render_as_string(
                    hide_password=False
                )
        return self._database_url

    @property
    def settings(self) -> Settings:
        """Settings on a migrated database, with attachments under the temp dir."""
        if self._settings is None:
            migrate.upgrade(self.database_url)
            self._settings = Settings(
                database_url=self.database_url,
                secret_key="test",
                insecure_cookies=True,
                attachments_dir=str(self.tmp / "attachments"),
            )
        return self._settings

    @property
    def app(self):
        """The app, with two orgs: acme (owner OWNER_EMAIL) and globex."""
        if self._app is None:
            create_admin(self.settings, OWNER_EMAIL, "Olive Owner", "acme", "Acme", PASSWORD)
            create_admin(self.settings, "other@example.com", "Gus Globex", "globex", "Globex", PASSWORD)
            self._app = create_app(self.settings, load_entry_points=False)
        return self._app

    def client(self) -> TestClient:
        """A new client on the app, closed with the Env."""
        client = TestClient(self.app)
        self._clients.append(client)
        return client

    @property
    def owner(self) -> TestClient:
        """A client signed in as the acme owner."""
        if self._owner is None:
            self._owner = self.client()
            login(self._owner)
        return self._owner

    def bearer(self, token: str) -> TestClient:
        client = self.client()
        client.headers["Authorization"] = f"Bearer {token}"
        return client

    def patch(self, target, attr: str, value):
        """Set ``target.attr`` to ``value`` until the Env closes (monkeypatch.setattr)."""
        patcher = mock.patch.object(target, attr, value)
        patcher.start()
        self._patches.append(patcher)
        return value

    def setenv(self, name: str, value: str) -> None:
        """Set an environment variable until the Env closes (monkeypatch.setenv)."""
        patcher = mock.patch.dict(os.environ, {name: value})
        patcher.start()
        self._patches.append(patcher)

    def delenv(self, name: str) -> None:
        """Remove an environment variable until the Env closes (monkeypatch.delenv(raising=False))."""
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        os.environ.pop(name, None)
        self._patches.append(patcher)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _OPEN.discard(self)
        try:
            while self._patches:
                self._patches.pop().stop()
            for client in self._clients:
                client.close()
            if self._app is not None:
                self._app.state.engine.dispose()
        finally:
            try:
                if self._pg_admin is not None:
                    with self._pg_admin.connect() as conn:
                        conn.execute(text(f'DROP DATABASE IF EXISTS "{self._pg_name}" WITH (FORCE)'))
                    self._pg_admin.dispose()
            finally:
                shutil.rmtree(self.tmp, ignore_errors=True)


def close_all() -> None:
    """Close every Env still open, e.g. after a test that skipped, since afterTest does not run then."""
    for env in list(_OPEN):
        env.close()


class RaisesInfo:
    value: BaseException | None = None


@contextmanager
def raises(expected, match: str | None = None):
    """Assert the block raises ``expected`` (and its message matches ``match``, by re.search)."""
    info = RaisesInfo()
    try:
        yield info
    except expected as error:
        if match is not None and not re.search(match, str(error)):
            raise AssertionError(f"{type(error).__name__}({error!s}) does not match {match!r}") from error
        info.value = error
        return
    raise AssertionError(f"did not raise {expected}")


def login(client: TestClient, email: str = OWNER_EMAIL, password: str = PASSWORD) -> dict:
    """Sign in with a cookie session; send the CSRF header on every later request, like the web UI does."""
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    return response.json()


def add_member(owner: TestClient, email: str, role: str, org: str = "acme") -> dict:
    response = owner.post(
        f"/api/v1/orgs/{org}/members",
        json={"email": email, "name": email.split("@")[0].title(), "role": role, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()
