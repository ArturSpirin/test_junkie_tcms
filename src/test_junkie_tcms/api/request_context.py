"""The request id and MCP tool of the request being served: the one source `audit.record` reads them from.

`RequestContextMiddleware` wraps every route. It gives each HTTP request an id (`req_` + a ULID), or keeps
the one the MCP dispatcher put in the scope for an in-process tool call, so every audit row a tool call
writes carries the id of the `/mcp` request the client sent. A client's `X-Request-ID` header is never read:
no client can set an ASGI scope key.
"""

from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import FastAPI

from test_junkie_tcms.db.base import new_id

# ASGI scope keys; the MCP dispatcher sets both on its in-process requests, and no client header can.
REQUEST_ID_KEY = "tcms.request_id"
MCP_TOOL_KEY = "tcms.mcp_tool"
HEADER = b"x-request-id"


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    tool: str | None


_current: ContextVar[RequestContext | None] = ContextVar("tcms_request", default=None)


def current() -> dict:
    """`{request_id, tool}` of the request being served; both None outside a request."""
    ctx = _current.get()
    if ctx is None:
        return {"request_id": None, "tool": None}
    return {"request_id": ctx.request_id, "tool": ctx.tool}


def new_request_id() -> str:
    return "req_" + new_id()


class RequestContextMiddleware:
    """Pure ASGI, HTTP only: sets the context for the request and sends its id as `X-Request-ID`."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = scope.get(REQUEST_ID_KEY) or new_request_id()
        scope[REQUEST_ID_KEY] = request_id

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != HEADER]
                message = {**message, "headers": [*headers, (HEADER, request_id.encode("latin-1"))]}
            await send(message)

        token = _current.set(RequestContext(request_id, scope.get(MCP_TOOL_KEY)))
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _current.reset(token)


def install(app: FastAPI) -> None:
    """Call after every other `add_middleware`: the last one added is the outermost."""
    app.add_middleware(RequestContextMiddleware)
