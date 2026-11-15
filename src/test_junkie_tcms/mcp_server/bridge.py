"""`test-junkie-tcms mcp`: a stdio MCP server that relays to a TCMS server's `/mcp` (PLAN-88).

For MCP clients that only start local stdio servers. It holds no tools of its own: `tools/list` and
`tools/call` go to the remote `/mcp` with the token, so the remote decides what the caller sees.
"""

import contextlib
from urllib.parse import urlencode

import httpx2
import mcp_types as types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from test_junkie_tcms import __version__


def mcp_url(base_url: str, toolsets: str | None) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/mcp"):
        url += "/mcp"
    url += "/"
    if toolsets:
        url += "?" + urlencode({"toolsets": toolsets})
    return url


async def run(base_url: str, token: str, toolsets: str | None = None) -> None:
    url = mcp_url(base_url, toolsets)
    async with contextlib.AsyncExitStack() as stack:
        http = await stack.enter_async_context(
            httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60)
        )
        read, write = await stack.enter_async_context(streamable_http_client(url, http_client=http))
        remote = await stack.enter_async_context(ClientSession(read, write))
        await remote.initialize()

        async def list_tools(ctx, params) -> types.ListToolsResult:
            return await remote.list_tools()

        async def call_tool(ctx, params) -> types.CallToolResult:
            return await remote.call_tool(params.name, params.arguments or {})

        server = Server(
            "test-junkie-tcms", version=__version__, on_list_tools=list_tools, on_call_tool=call_tool
        )
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())
