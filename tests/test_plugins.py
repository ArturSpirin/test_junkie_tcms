"""Plugin seams: the app boots with none, and a plugin can mount routes and set audit retention."""

from fastapi import APIRouter
from fastapi.testclient import TestClient
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.api.operations import operation
from test_junkie_tcms.plugins import PluginContext, RetentionPolicy
from tests import support


@Suite(parameters=support.DATABASES)
class Plugins:
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
    def test_boots_without_plugins(self, suite_parameter):
        app = self.env.app
        assert app.state.plugins == []
        assert app.state.audit_retention == RetentionPolicy(days=90)
        with TestClient(app) as client:
            assert client.get("/healthz").json() == {"status": "ok"}
            assert client.get("/api/v1/openapi.json").status_code == 200

    @test()
    def test_plugin_mounts_routes_and_sets_retention(self, suite_parameter):
        app = self.env.app
        router = APIRouter()

        # Plugin routes carry the same marker as the core API; the MCP server won't start without it.
        @router.get("/ping", **operation("example_ping", None, "core", mcp=False))
        def ping() -> dict:
            return {"pong": True}

        ctx = PluginContext(app, "example")
        ctx.add_router(router)
        ctx.set_audit_retention(RetentionPolicy(days=365))
        assert app.state.audit_retention.days == 365
        with TestClient(app) as client:
            assert client.get("/api/v1/ext/example/ping").json() == {"pong": True}

    @test(parameters=["add_auth_provider", "add_admin_capability", "add_ui_extension"])
    def test_later_seams_are_declared(self, suite_parameter, parameter):
        app, seam = self.env.app, parameter
        with support.raises(NotImplementedError):
            getattr(PluginContext(app, "example"), seam)(object())
