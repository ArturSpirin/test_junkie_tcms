"""Every database test runs on SQLite, and on Postgres too when TJ_TCMS_TEST_POSTGRES_URL is set."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from test_junkie_tcms.app import create_app
from test_junkie_tcms.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from test_junkie_tcms.cli import create_admin
from test_junkie_tcms.db import migrate
from test_junkie_tcms.settings import Settings

POSTGRES_URL = os.environ.get("TJ_TCMS_TEST_POSTGRES_URL")
OWNER_EMAIL = "owner@example.com"
PASSWORD = "correct horse battery"


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgres",
            marks=pytest.mark.skipif(not POSTGRES_URL, reason="TJ_TCMS_TEST_POSTGRES_URL is not set"),
        ),
    ]
)
def database_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{(tmp_path / 'tcms.db').as_posix()}"
        return
    admin_url = make_url(POSTGRES_URL)
    name = f"tcms_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield admin_url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def settings(database_url):
    migrate.upgrade(database_url)
    return Settings(database_url=database_url, secret_key="test", insecure_cookies=True)


@pytest.fixture
def app(settings):
    create_admin(settings, OWNER_EMAIL, "Olive Owner", "acme", "Acme", PASSWORD)
    create_admin(settings, "other@example.com", "Gus Globex", "globex", "Globex", PASSWORD)
    app = create_app(settings, load_entry_points=False)
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client_factory(app):
    clients = []

    def make() -> TestClient:
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def login(client: TestClient, email: str = OWNER_EMAIL, password: str = PASSWORD) -> dict:
    """Sign in with a cookie session; send the CSRF header on every later request, like the web UI does."""
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    return response.json()


@pytest.fixture
def owner(client_factory):
    client = client_factory()
    login(client)
    return client


def bearer(client_factory, token: str) -> TestClient:
    client = client_factory()
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def add_member(owner: TestClient, email: str, role: str, org: str = "acme") -> dict:
    response = owner.post(
        f"/api/v1/orgs/{org}/members",
        json={"email": email, "name": email.split("@")[0].title(), "role": role, "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()
