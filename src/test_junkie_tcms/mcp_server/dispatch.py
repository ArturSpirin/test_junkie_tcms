"""Run one tool call as an in-process request through the real API.

Auth, scopes, If-Match, idempotency and the audit all stay in the API: the dispatcher only turns tool args
back into a request. It is the one server module that imports `httpx2`, which `mcp` itself requires; the
API and its tests stay on `httpx`.
"""

import base64
import json
from urllib.parse import quote

import httpx2

from test_junkie_tcms.auth.deps import MCP_VIA_KEY
from test_junkie_tcms.mcp_server.generator import ToolSpec

BASE_URL = "http://tcms.internal"


class _Marked:
    """Marks the in-process request as coming over MCP. A client can't set an ASGI scope key."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        scope = {**scope, MCP_VIA_KEY: True}
        await self.app(scope, receive, send)


def _error(status: int, title: str, detail: str) -> dict:
    return {
        "status": status,
        "error": {"type": "about:blank", "title": title, "status": status, "detail": detail},
    }


def check_args(tool: ToolSpec, arguments: dict) -> dict | None:
    """An error envelope for unknown or missing args, else None."""
    unknown = sorted(set(arguments) - set(tool.args))
    if unknown:
        return _error(422, "Unprocessable Entity", f"Unknown args: {', '.join(unknown)}")
    missing = sorted(tool.required - set(arguments))
    if missing:
        return _error(422, "Unprocessable Entity", f"Missing required args: {', '.join(missing)}")
    return None


def build_request(tool: ToolSpec, arguments: dict, token: str) -> dict:
    """The method, url, params, headers and body one call becomes."""
    path = tool.path
    params: dict = {}
    headers = {"Authorization": f"Bearer {token}"}
    body: dict = {}
    for arg, value in arguments.items():
        spec = tool.args[arg]
        if spec.location == "path":
            path = path.replace("{" + spec.wire + "}", quote(str(value), safe=""))
        elif spec.location == "query":
            if value is not None:
                params[spec.wire] = value
        elif spec.location == "header":
            if value is not None:
                headers[spec.wire] = f'"{value}"' if arg == "expected_version" else str(value)
        else:
            body[spec.wire] = value
    content = None
    if any(spec.location == "body" for spec in tool.args.values()):
        # Canonical JSON: the idempotency hash covers the raw body, so a retry with the args in another
        # order must send the same bytes.
        content = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    return {"method": tool.method, "url": path, "params": params, "headers": headers, "content": content}


def envelope(response) -> dict:
    """`{status, data|error, etag?, replayed?}` from the API response. A body that is neither JSON nor
    text (an md-bundle zip) arrives as `{content_type, base64}`."""
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if (
        response.content
        and content_type
        and not content_type.startswith("text/")
        and "json" not in content_type
    ):
        payload = {"content_type": content_type, "base64": base64.b64encode(response.content).decode()}
    else:
        try:
            payload = response.json() if response.content else None
        except ValueError:
            payload = response.text
    result: dict = {"status": response.status_code}
    if response.status_code >= 400:
        result["error"] = payload
        return result
    result["data"] = payload
    etag = response.headers.get("ETag")
    if etag:
        result["etag"] = etag
    if response.headers.get("Idempotent-Replayed") == "true":
        result["replayed"] = True
    return result


async def dispatch(app, tool: ToolSpec, arguments: dict, token: str) -> dict:
    """Call the API for one tool and return its envelope; `status` >= 400 means the call failed."""
    bad = check_args(tool, arguments)
    if bad is not None:
        return bad
    request = build_request(tool, arguments, token)
    transport = httpx2.ASGITransport(app=_Marked(app), raise_app_exceptions=False)
    async with httpx2.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.request(**request)
    return envelope(response)
