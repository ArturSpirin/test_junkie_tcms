"""Plugin seams: the app boots with none, and a plugin can mount routes and set audit retention."""

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from test_junkie_tcms.plugins import PluginContext, RetentionPolicy


def test_boots_without_plugins(app):
    assert app.state.plugins == []
    assert app.state.audit_retention == RetentionPolicy(days=90)
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/v1/openapi.json").status_code == 200


def test_plugin_mounts_routes_and_sets_retention(app):
    router = APIRouter()

    @router.get("/ping")
    def ping() -> dict:
        return {"pong": True}

    ctx = PluginContext(app, "example")
    ctx.add_router(router)
    ctx.set_audit_retention(RetentionPolicy(days=365))
    assert app.state.audit_retention.days == 365
    with TestClient(app) as client:
        assert client.get("/api/v1/ext/example/ping").json() == {"pong": True}


@pytest.mark.parametrize("seam", ["add_auth_provider", "add_admin_capability", "add_ui_extension"])
def test_later_seams_are_declared(app, seam):
    with pytest.raises(NotImplementedError):
        getattr(PluginContext(app, "example"), seam)(object())
