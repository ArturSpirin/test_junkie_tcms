"""T5 drift guard: every API route carries `op()`, every MCP route has a tool, and the tools match the routes.

`drift()` reads the routes' FastAPI params, so it fails when a tool and its operation disagree. The snapshot
pins the generated tool list; regenerate it with `TCMS_UPDATE_MCP_SNAPSHOT=1` after an intended change.
"""

import dataclasses
import json
import os
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends

from test_junkie_tcms.api.operations import operation
from test_junkie_tcms.auth.deps import Principal, get_principal
from test_junkie_tcms.auth.scopes import READ
from test_junkie_tcms.mcp_server.generator import (
    ArgSpec,
    GeneratorError,
    build_tools,
    drift,
    unmarked_routes,
)
from test_junkie_tcms.plugins import PluginContext

SNAPSHOT = Path(__file__).parent / "snapshots" / "mcp_tools.json"


def _as_json(tools) -> list[dict]:
    return [dataclasses.asdict(tool) for tool in tools]


def demo_router() -> APIRouter:
    """A sample plugin router, marked like the core API."""
    router = APIRouter()

    @router.get("/greet", **operation("demo_greet", READ, "core"))
    def greet(name: str, principal: Principal = Depends(get_principal)) -> dict:
        return {"hello": name, "via": principal.via}

    return router


def test_every_api_route_is_marked_and_the_tools_match_the_routes(app):
    assert unmarked_routes(app) == []
    tools = build_tools(app)
    assert drift(app, tools) == []
    assert len(tools) == 84


def test_tools_match_the_snapshot(app):
    current = _as_json(build_tools(app))
    if os.environ.get("TCMS_UPDATE_MCP_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert current == json.loads(SNAPSHOT.read_text(encoding="utf-8")), (
        "MCP tools changed; if intended, rerun with TCMS_UPDATE_MCP_SNAPSHOT=1 and commit the snapshot"
    )


def _replace(tools, name: str, change):
    """The tools with `name` changed by `change(tool) -> fields`."""
    return [dataclasses.replace(t, **change(t)) if t.name == name else t for t in tools]


def test_drift_fails_on_a_dropped_arg(app):
    tools = build_tools(app)

    def drop(t):
        args = {k: v for k, v in t.args.items() if k != "expected_version"}
        props = {k: v for k, v in t.input_schema["properties"].items() if k != "expected_version"}
        schema = {
            **t.input_schema,
            "properties": props,
            "required": sorted(t.required - {"expected_version"}),
        }
        return {"args": args, "input_schema": schema}

    assert drift(app, _replace(tools, "cases_update", drop)) == [
        "cases_update: route arg 'expected_version' missing from the tool",
        "cases_update: required ['case', 'org'] != route ['case', 'expected_version', 'org']",
    ]


def test_drift_fails_on_a_changed_path_scope_or_wire_name(app):
    tools = build_tools(app)
    path = next(t.path for t in tools if t.name == "cases_get")
    moved = _replace(tools, "cases_get", lambda t: {"path": t.path + "/x"})
    assert drift(app, moved) == [f"cases_get: path {path}/x != route {path}"]
    rescoped = _replace(tools, "cases_get", lambda t: {"scope": "admin"})
    assert drift(app, rescoped) == ["cases_get: scope admin != route read"]
    rewired = _replace(
        tools, "cases_update", lambda t: {"args": {**t.args, "expected_version": ArgSpec("header", "ETag")}}
    )
    assert any("arg 'expected_version'" in line for line in drift(app, rewired))


def test_drift_fails_on_a_tool_without_a_route_and_a_route_without_a_tool(app):
    tools = build_tools(app)
    ghost = dataclasses.replace(next(t for t in tools if t.name == "me_get"), name="ghost_get")
    assert drift(app, [*tools, ghost]) == ["ghost_get: tool has no route"]
    assert drift(app, [t for t in tools if t.name != "me_get"]) == ["me_get: route has no tool"]


# Plugin routers under /api/v1/ext


def test_a_marked_ext_route_becomes_a_tool_the_guard_covers(app):
    PluginContext(app, "demo").add_router(demo_router())
    assert unmarked_routes(app) == []
    tools = build_tools(app)
    [greet] = [t for t in tools if t.name == "demo_greet"]
    assert (greet.method, greet.path, greet.scope, greet.toolset) == (
        "GET",
        "/api/v1/ext/demo/greet",
        READ,
        "core",
    )
    assert greet.args == {"name": ArgSpec("query", "name")} and greet.required == {"name"}
    assert drift(app, tools) == []
    renamed = _replace(tools, "demo_greet", lambda t: {"args": {"who": ArgSpec("query", "who")}})
    assert "demo_greet: route arg 'name' missing from the tool" in drift(app, renamed)


def test_an_unmarked_ext_route_fails_the_guard(app):
    router = APIRouter()

    @router.get("/ping")
    def ping() -> dict:
        return {"pong": True}

    PluginContext(app, "demo").add_router(router)
    assert unmarked_routes(app) == ["GET /api/v1/ext/demo/ping"]
    with pytest.raises(GeneratorError, match="/api/v1/ext/demo/ping"):
        build_tools(app)


def test_a_marked_ext_route_hidden_from_the_schema_fails_the_guard(app):
    router = APIRouter()

    @router.get("/secret", include_in_schema=False, **operation("demo_secret", READ, "core"))
    def secret() -> dict:
        return {}

    PluginContext(app, "demo").add_router(router)
    assert unmarked_routes(app) == ["GET /api/v1/ext/demo/secret"]
    with pytest.raises(GeneratorError, match="/api/v1/ext/demo/secret"):
        build_tools(app)
