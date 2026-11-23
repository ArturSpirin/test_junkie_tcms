"""The CLI's database commands work on a fresh, unmigrated database: each one migrates it first."""

import contextlib
import io

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms import cli
from test_junkie_tcms.app import create_app
from test_junkie_tcms.db.models import Actor, Membership, Org, User
from test_junkie_tcms.db.session import make_engine, make_sessionmaker
from test_junkie_tcms.settings import Settings
from tests import support

EMAIL = "admin@example.com"


def run(*argv: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.main(list(argv))
    return out.getvalue().strip()


@Suite(parameters=support.DATABASES)
class Cli:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)
        # env.database_url is a fresh database with no tables; env.settings would migrate it, so it's unused.
        self.env.setenv("TJ_TCMS_DATABASE_URL", self.env.database_url)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    @test()
    def test_create_admin_on_a_fresh_database(self, suite_parameter):
        self.env.setenv("TJ_TCMS_ADMIN_PASSWORD", support.PASSWORD)
        args = ["--email", EMAIL, "--name", "Ada Admin", "--org-slug", "acme", "--org-name", "Acme"]
        assert run("create-admin", *args) == f"Created {EMAIL} as owner of acme"

        engine = make_engine(self.env.database_url)
        try:
            with make_sessionmaker(engine)() as db:
                user = db.scalar(select(User).where(User.email == EMAIL))
                org = db.scalar(select(Org).where(Org.slug == "acme"))
                assert user is not None and org is not None
                membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
                assert (membership.org_id, membership.role) == (org.id, "owner")
                actor = db.scalar(select(Actor).where(Actor.user_id == user.id))
                assert (actor.org_id, actor.kind) == (org.id, "user")
        finally:
            engine.dispose()

        settings = Settings(database_url=self.env.database_url, secret_key="test", insecure_cookies=True)
        app = create_app(settings, load_entry_points=False)
        try:
            with TestClient(app) as client:
                support.login(client, email=EMAIL)
        finally:
            app.state.engine.dispose()

    @test()
    def test_sweep_idempotency_on_a_fresh_database(self, suite_parameter):
        assert run("sweep-idempotency") == "Deleted 0 expired idempotency records"
