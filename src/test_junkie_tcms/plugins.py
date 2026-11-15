"""Plugin seams.

A plugin is an entry point in the `test_junkie_tcms.plugins` group pointing at `register(ctx)`. T1 wires
`add_router` and `set_audit_retention`; the other seams are declared and arrive with later tasks.
"""

import logging
from dataclasses import dataclass
from importlib.metadata import entry_points

from fastapi import APIRouter, FastAPI

ENTRY_POINT_GROUP = "test_junkie_tcms.plugins"
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionPolicy:
    days: int = 90


class PluginContext:
    def __init__(self, app: FastAPI, plugin: str):
        self.app = app
        self.plugin = plugin

    def add_router(self, router: APIRouter, prefix: str = "") -> None:
        """Mount plugin routes under `/api/v1/ext/<plugin><prefix>`.

        Every route needs the same marker as the core API, `**operation(id, scope, toolset, mcp=...)` from
        `test_junkie_tcms.api.operations`; the app refuses to start the MCP server, and the drift guard
        fails, on an unmarked one. Marked routes become MCP tools like any other.
        """
        self.app.include_router(router, prefix=f"/api/v1/ext/{self.plugin}{prefix}")

    def set_audit_retention(self, policy: RetentionPolicy) -> None:
        self.app.state.audit_retention = policy

    def add_auth_provider(self, provider) -> None:
        raise NotImplementedError("auth providers arrive after T1")

    def add_admin_capability(self, capability) -> None:
        raise NotImplementedError("admin capabilities arrive after T1")

    def add_ui_extension(self, extension) -> None:
        raise NotImplementedError("UI extensions arrive with the web UI")


def load_plugins(app: FastAPI) -> list[str]:
    loaded = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        register = ep.load()
        register(PluginContext(app, ep.name))
        loaded.append(ep.name)
        log.info("loaded plugin %s", ep.name)
    return loaded
