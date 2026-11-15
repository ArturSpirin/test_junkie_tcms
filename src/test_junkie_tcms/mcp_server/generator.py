"""Build one MCP tool per `op()`-marked API operation from the app's OpenAPI document (PLAN-27 §4, PLAN-88).

Tool args are the operation's path and query params, its declared headers (`If-Match` → `expected_version`,
`Idempotency-Key` → `idempotency_key`) and the fields of its JSON body, flattened to the top level. A
`ToolSpec` keeps everything the dispatcher needs, so nothing re-reads OpenAPI at call time. Anything the
generator can't map fails here, at startup and in CI, never on a call.
"""

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field

import mcp_types as types
from fastapi import FastAPI, params
from fastapi.dependencies.utils import get_flat_params
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel

from test_junkie_tcms.api.operations import TOOLSETS

API_PREFIX = "/api/v1"
METHODS = ("get", "post", "put", "patch", "delete")
# Declared request headers and the tool arg each becomes.
HEADER_ARGS = {"If-Match": "expected_version", "Idempotency-Key": "idempotency_key"}
DESTRUCTIVE_SUFFIXES = ("_archive", "_revoke", "_disable", "_delete")
REF_PREFIX = "#/components/schemas/"


class GeneratorError(Exception):
    pass


@dataclass(frozen=True)
class ArgSpec:
    location: str  # "path", "query", "header" or "body"
    wire: str  # the path/query param name, header name or body field


@dataclass(frozen=True)
class ToolSpec:
    name: str
    method: str
    path: str
    scope: str | None
    toolset: str
    description: str
    input_schema: dict
    annotations: dict
    args: dict[str, ArgSpec] = field(default_factory=dict)

    @property
    def required(self) -> frozenset[str]:
        return frozenset(self.input_schema.get("required", []))


def api_routes(app: FastAPI) -> list:
    """Every API route under `/api/v1`, hidden ones included, as FastAPI route contexts.

    Walks `app.routes`, not `app.openapi()`: a route with `include_in_schema=False` is absent from the
    document but still answers. `iter_route_contexts` flattens included routers, which `app.routes` keeps
    nested.
    """
    return [
        rc
        for rc in iter_route_contexts(app.routes)
        if isinstance(rc.original_route, APIRoute) and rc.path.startswith(API_PREFIX)
    ]


def unmarked_routes(app: FastAPI) -> list[str]:
    """`METHOD path` of every API route without a complete `op()` marker, or a hidden MCP route."""
    missing = []
    for route in api_routes(app):
        extra = route.openapi_extra or {}
        marked = (
            route.operation_id
            and {"x-scope", "x-mcp", "x-toolset"} <= extra.keys()
            and (not extra["x-mcp"] or extra["x-toolset"] in TOOLSETS)
        )
        if not marked or (extra.get("x-mcp") and not route.include_in_schema):
            missing.extend(f"{m} {route.path}" for m in sorted(route.methods))
    return missing


def _refs(node, found: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(REF_PREFIX):
            found.add(ref[len(REF_PREFIX) :])
        for value in node.values():
            _refs(value, found)
    elif isinstance(node, list):
        for value in node:
            _refs(value, found)


def _rewrite_refs(node):
    if isinstance(node, dict):
        return {
            k: ("#/$defs/" + v[len(REF_PREFIX) :] if k == "$ref" and isinstance(v, str) else _rewrite_refs(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_refs(v) for v in node]
    return node


def _defs_for(schema_parts, components: dict) -> dict:
    """The component schemas the parts reference, transitively, under `$defs` (keeps recursive types)."""
    pending: set[str] = set()
    _refs(schema_parts, pending)
    defs: dict[str, dict] = {}
    while pending:
        name = pending.pop()
        if name in defs:
            continue
        if name not in components:
            raise GeneratorError(f"unknown schema {name}")
        defs[name] = components[name]
        more: set[str] = set()
        _refs(components[name], more)
        pending |= more - defs.keys()
    return {k: _rewrite_refs(v) for k, v in sorted(defs.items())}


def _resolve(schema: dict, components: dict) -> dict:
    ref = schema.get("$ref")
    if ref:
        return components[ref[len(REF_PREFIX) :]]
    return schema


def _annotations(method: str, name: str, header_args: set[str]) -> dict:
    return {
        "read_only_hint": method == "GET",
        "destructive_hint": method == "DELETE" or name.endswith(DESTRUCTIVE_SUFFIXES) or "_remove" in name,
        "idempotent_hint": method in ("GET", "PUT") or "idempotency_key" in header_args,
    }


def _tool(method: str, path: str, o: dict, components: dict) -> ToolSpec:
    name = o["operationId"]
    props: dict[str, dict] = {}
    required: list[str] = []
    args: dict[str, ArgSpec] = {}

    def add(arg: str, spec: ArgSpec, schema: dict, is_required: bool) -> None:
        if arg in args:
            raise GeneratorError(
                f"{name}: arg {arg!r} comes from both {args[arg].location} and {spec.location}"
            )
        args[arg] = spec
        props[arg] = schema
        if is_required:
            required.append(arg)

    for p in o.get("parameters", []):
        loc = p["in"]
        schema = copy.deepcopy(p.get("schema", {}))
        schema.pop("title", None)
        if p.get("description"):
            schema.setdefault("description", p["description"])
        if loc in ("path", "query"):
            add(p["name"], ArgSpec(loc, p["name"]), schema, p.get("required", False))
        elif loc == "header" and p["name"] in HEADER_ARGS:
            arg = HEADER_ARGS[p["name"]]
            if arg == "expected_version":
                schema = {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "The version you last read; a stale one fails with 409 and current_version"
                    ),
                }
            add(arg, ArgSpec("header", p["name"]), schema, p.get("required", False))
        else:
            raise GeneratorError(f"{name}: {loc} parameter {p['name']!r} has no tool arg mapping")

    body = o.get("requestBody")
    if body:
        content = body.get("content", {})
        if list(content) != ["application/json"]:
            raise GeneratorError(f"{name}: only JSON bodies become tool args, got {list(content)}")
        body_schema = _resolve(content["application/json"]["schema"], components)
        if body_schema.get("type") != "object" or "properties" not in body_schema:
            raise GeneratorError(f"{name}: the JSON body must be an object with properties")
        body_required = set(body_schema.get("required", [])) if body.get("required") else set()
        for field_name, field_schema in body_schema["properties"].items():
            schema = copy.deepcopy(field_schema)
            schema.pop("title", None)
            add(field_name, ArgSpec("body", field_name), schema, field_name in body_required)

    input_schema: dict = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        input_schema["required"] = sorted(required)
    defs = _defs_for(props, components)
    input_schema = _rewrite_refs(input_schema)
    if defs:
        input_schema["$defs"] = defs

    description = o.get("summary", name)
    if o.get("description"):
        description = f"{description}. {o['description']}"
    return ToolSpec(
        name=name,
        method=method.upper(),
        path=path,
        scope=o.get("x-scope"),  # OpenAPI drops a None scope (routes any member may call)
        toolset=o["x-toolset"],
        description=description,
        input_schema=input_schema,
        annotations=_annotations(method.upper(), name, set(args)),
        args=args,
    )


def build_tools(app: FastAPI) -> list[ToolSpec]:
    """Every MCP tool the app's operations define, sorted by name; raises `GeneratorError` on any gap."""
    missing = unmarked_routes(app)
    if missing:
        raise GeneratorError(
            "routes without an op() marker, or MCP routes hidden from the schema: " + ", ".join(missing)
        )
    app.openapi_schema = None  # plugins may have added routes since the last call
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})
    tools: dict[str, ToolSpec] = {}
    for path, item in spec["paths"].items():
        if not path.startswith(API_PREFIX):
            continue
        for method, o in item.items():
            if method not in METHODS or not o.get("x-mcp"):
                continue
            tool = _tool(method, path, o, components)
            if tool.name in tools:
                raise GeneratorError(f"duplicate tool name {tool.name}")
            tools[tool.name] = tool
    return [tools[name] for name in sorted(tools)]


def mcp_tool(tool: ToolSpec) -> types.Tool:
    """The tool as `tools/list` sends it."""
    return types.Tool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        annotations=types.ToolAnnotations(**tool.annotations),
    )


def definition(tool: ToolSpec) -> dict:
    """The tool's `tools/list` entry as wire JSON (camelCase keys)."""
    return mcp_tool(tool).model_dump(mode="json", by_alias=True, exclude_none=True)


def def_tokens(tool: ToolSpec) -> int:
    """≈ tokens the tool's definition costs an agent: compact JSON bytes ÷ 4, rounded up (PLAN-100)."""
    return math.ceil(len(json.dumps(definition(tool), separators=(",", ":")).encode()) / 4)


def tool_list_hash(tools: list[ToolSpec]) -> str:
    """sha256 of every tool definition as canonical JSON, by name: changes when any tool does."""
    defs = [definition(tool) for tool in sorted(tools, key=lambda t: t.name)]
    return hashlib.sha256(json.dumps(defs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _route_args(route) -> tuple[dict[str, ArgSpec], set[str], list[str]]:
    """The tool args a route's FastAPI params call for, which are required, and any it can't map."""
    args: dict[str, ArgSpec] = {}
    required: set[str] = set()
    problems: list[str] = []
    for p in get_flat_params(route.dependant):
        info = p.field_info
        if isinstance(info, params.Path):
            arg, spec = p.alias, ArgSpec("path", p.alias)
        elif isinstance(info, params.Query):
            arg, spec = p.alias, ArgSpec("query", p.alias)
        elif isinstance(info, params.Header) and p.alias in HEADER_ARGS:
            arg, spec = HEADER_ARGS[p.alias], ArgSpec("header", p.alias)
        else:
            problems.append(f"{type(info).__name__.lower()} param {p.alias!r} has no tool arg")
            continue
        args[arg] = spec
        if info.is_required():
            required.add(arg)
    body = route.body_field
    if body is not None:
        model = body.field_info.annotation
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            problems.append(f"body {model!r} is not a model")
        else:
            for name, f in model.model_fields.items():
                wire = f.alias or name
                args[wire] = ArgSpec("body", wire)
                if body.field_info.is_required() and f.is_required():
                    required.add(wire)
    return args, required, problems


def drift(app: FastAPI, tools: list[ToolSpec]) -> list[str]:
    """Every way `tools` disagree with the app's marked routes; empty when they match.

    Reads the routes' FastAPI params and body models, not OpenAPI, so it checks the generator rather than
    repeating it: a tool that lost an arg, moved path or method, changed scope or toolset, or has no route
    (and a marked route with no tool) each give one line.
    """
    by_name = {t.name: t for t in tools}
    seen: set[str] = set()
    out: list[str] = []
    for route in api_routes(app):
        extra = route.openapi_extra or {}
        if not extra.get("x-mcp"):
            continue
        name = route.operation_id
        seen.add(name)
        tool = by_name.get(name)
        if tool is None:
            out.append(f"{name}: route has no tool")
            continue
        if {tool.method} != set(route.methods):
            out.append(f"{name}: method {tool.method} != route {sorted(route.methods)}")
        if tool.path != route.path:
            out.append(f"{name}: path {tool.path} != route {route.path}")
        if tool.scope != extra.get("x-scope"):
            out.append(f"{name}: scope {tool.scope} != route {extra.get('x-scope')}")
        if tool.toolset != extra.get("x-toolset"):
            out.append(f"{name}: toolset {tool.toolset} != route {extra.get('x-toolset')}")
        args, required, problems = _route_args(route)
        out.extend(f"{name}: {p}" for p in problems)
        for arg in sorted(args.keys() - tool.args.keys()):
            out.append(f"{name}: route arg {arg!r} missing from the tool")
        for arg in sorted(tool.args.keys() - args.keys()):
            out.append(f"{name}: tool arg {arg!r} not on the route")
        for arg in sorted(args.keys() & tool.args.keys()):
            if args[arg] != tool.args[arg]:
                out.append(f"{name}: arg {arg!r} is {tool.args[arg]} on the tool, {args[arg]} on the route")
        if tool.required != required:
            out.append(f"{name}: required {sorted(tool.required)} != route {sorted(required)}")
        if set(tool.input_schema.get("properties", {})) != tool.args.keys():
            out.append(f"{name}: input schema properties differ from the tool args")
    out.extend(f"{name}: tool has no route" for name in sorted(by_name.keys() - seen))
    return out
