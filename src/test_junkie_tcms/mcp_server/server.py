"""The `/mcp` endpoint: a stateless streamable-HTTP MCP server over the generated tools.

`McpEndpoint` is mounted at `/mcp` when the app is made. It authenticates the bearer token itself (401, or
403 for a consumer token, as `get_principal` does), works out the caller's effective scopes and toolsets,
closes that DB session, and only then hands the request to the MCP server. The server and its tools are
built in the app's lifespan, after plugins have added their routers.
"""

import contextlib
import json
from dataclasses import dataclass, replace
from urllib.parse import parse_qs

import anyio.to_thread
import mcp_types as types
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from test_junkie_tcms import __version__
from test_junkie_tcms.api.operations import TOOLSETS
from test_junkie_tcms.auth import tokens
from test_junkie_tcms.auth.deps import effective_role
from test_junkie_tcms.auth.scopes import ADMIN, AUDIT_READ, CONSUMER, ROLE_SCOPES
from test_junkie_tcms.mcp_server import stats
from test_junkie_tcms.mcp_server.dispatch import dispatch
from test_junkie_tcms.mcp_server.generator import ToolSpec, build_tools, mcp_tool, tool_list_hash

CALLER_KEY = "tcms.mcp"
ALWAYS_ON = "core"


@dataclass(frozen=True)
class Caller:
    token: str
    scopes: frozenset[str]
    toolsets: frozenset[str]
    org_id: str
    actor_id: str


class ToolsetError(ValueError):
    pass


def parse_toolsets(value: str) -> frozenset[str]:
    """`all` or a comma list of toolset names; `core` is always added."""
    names = {name.strip() for name in value.split(",") if name.strip()}
    if "all" in names:
        return frozenset(TOOLSETS)
    unknown = sorted(names - set(TOOLSETS))
    if unknown:
        raise ToolsetError(f"Unknown toolsets: {', '.join(unknown)}")
    return frozenset(names | {ALWAYS_ON})


def refusal(tool: ToolSpec, caller: Caller) -> tuple[int, str] | None:
    """Why the caller can't use the tool, as (status, detail), or None when it can.

    Scope comes first: reconnecting with another toolset can't add a scope the caller lacks."""
    # The tools marked audit:read take admin too (require_any_scope), so admin passes them.
    if tool.scope == AUDIT_READ:
        if not {AUDIT_READ, ADMIN} & caller.scopes:
            return 403, f"Needs scope {ADMIN} or {AUDIT_READ}"
    elif tool.scope is not None and tool.scope not in caller.scopes:
        return 403, f"Needs scope {tool.scope}"
    if tool.toolset not in caller.toolsets:
        return 403, (
            f"{tool.name} is in toolset {tool.toolset}: "
            f"connect with ?toolsets={tool.toolset} or ?toolsets=all"
        )
    return None


def visible(tool: ToolSpec, caller: Caller) -> bool:
    return refusal(tool, caller) is None


def _problem(status: int, title: str, detail: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        {"type": "about:blank", "title": title, "status": status, "detail": detail},
        status_code=status,
        headers=headers,
        media_type="application/problem+json",
    )


def _resolve(app: FastAPI, value: str) -> tuple[int, str] | Caller:
    """The caller with its effective scopes (role ∩ token scopes), or (status, detail) when it is refused.

    Its toolsets are filled in from the query string afterwards."""
    db = app.state.sessionmaker()
    try:
        found = tokens.authenticate_token(db, value)
        if found is None:
            return 401, "Invalid, revoked or expired token"
        token, actor = found
        if CONSUMER in token.scopes:
            return 403, "A consumer token reaches only the consumer routes"
        role = effective_role(db, actor)
        scopes = frozenset() if role is None else ROLE_SCOPES[role] & frozenset(token.scopes)
        return Caller(
            token=value, scopes=scopes, toolsets=frozenset(), org_id=actor.org_id, actor_id=actor.id
        )
    finally:
        db.close()  # closed before the call dispatches, so the inner request never waits on it


class McpEndpoint:
    """ASGI app at `/mcp`: bearer auth and caller scopes, then the MCP server built in the lifespan."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.sub = None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return
        response = await self._authenticate(scope)
        if response is not None:
            await response(scope, receive, send)
            return
        await self.sub(scope, receive, send)

    async def _authenticate(self, scope) -> JSONResponse | None:
        if self.sub is None:
            return _problem(503, "Service Unavailable", "The MCP server starts with the app's lifespan")
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        scheme, _, value = headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            return _problem(401, "Unauthorized", "Not authenticated", {"WWW-Authenticate": "Bearer"})
        value = value.strip()
        resolved = await anyio.to_thread.run_sync(_resolve, self.app, value)
        if isinstance(resolved, tuple):
            status, detail = resolved
            if status == 401:
                return _problem(401, "Unauthorized", detail, {"WWW-Authenticate": "Bearer"})
            return _problem(status, "Forbidden", detail)
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        wanted = query.get("toolsets", [self.app.state.settings.mcp_default_toolsets])[-1]
        try:
            toolsets = parse_toolsets(wanted)
        except ToolsetError as exc:
            return _problem(400, "Bad Request", str(exc))
        scope[CALLER_KEY] = replace(resolved, toolsets=toolsets)
        return None


def _error(status: int, title: str, detail: str) -> dict:
    return {
        "status": status,
        "error": {"type": "about:blank", "title": title, "status": status, "detail": detail},
    }


def _result(envelope: dict) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(envelope, default=str))],
        structured_content=envelope,
        is_error=envelope["status"] >= 400,
    )


def make_server(app: FastAPI, tools: list[ToolSpec]) -> Server:
    by_name = {tool.name: tool for tool in tools}

    async def list_tools(ctx, params) -> types.ListToolsResult:
        caller: Caller = ctx.request.scope[CALLER_KEY]
        return types.ListToolsResult(tools=[mcp_tool(tool) for tool in tools if visible(tool, caller)])

    async def call_tool(ctx, params) -> types.CallToolResult:
        caller: Caller = ctx.request.scope[CALLER_KEY]
        tool = by_name.get(params.name)
        if tool is None:
            return _result(_error(404, "Not Found", f"Unknown tool {params.name}"))
        refused = refusal(tool, caller)
        if refused is not None:  # it exists but this caller can't use it: say why, and don't record it
            status, detail = refused
            return _result(_error(status, "Forbidden", detail))
        result = _result(await dispatch(app, tool, params.arguments or {}, caller.token))
        size = len(result.content[0].text.encode())
        await anyio.to_thread.run_sync(
            stats.safe_record,
            app.state.sessionmaker,
            caller.org_id,
            caller.actor_id,
            tool.name,
            result.is_error,
            size,
        )
        return result

    return Server("test-junkie-tcms", version=__version__, on_list_tools=list_tools, on_call_tool=call_tool)


def _transport_security(allowed_hosts: str) -> TransportSecuritySettings:
    hosts = [host.strip() for host in allowed_hosts.split(",") if host.strip()]
    if not hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts)


def install(app: FastAPI) -> McpEndpoint:
    """Mount `/mcp`; call `lifespan(app)` from the app's lifespan to build and run it."""
    endpoint = McpEndpoint(app)
    app.mount("/mcp", endpoint)
    app.state.mcp = endpoint
    return endpoint


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the tools from the routes as they are now, and run a fresh MCP server until shutdown."""
    endpoint: McpEndpoint = app.state.mcp
    tools = build_tools(app)
    server = make_server(app, tools)  # a session manager runs once, so every lifespan gets its own
    endpoint.sub = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=_transport_security(app.state.settings.mcp_allowed_hosts),
    )
    app.state.mcp_tools = tools
    app.state.mcp_tool_hash = tool_list_hash(tools)
    try:
        async with server.session_manager.run():
            yield
    finally:
        endpoint.sub = None
