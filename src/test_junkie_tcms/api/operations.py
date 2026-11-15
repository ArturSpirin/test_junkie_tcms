"""Route metadata the MCP generator (T5) reads: operationId, scope, toolset and whether it is a tool.

Every route under `/api/v1`, plugin routers under `/api/v1/ext` included, spreads `**op(...)` (or its alias
`**operation(...)`) into its decorator; the drift guard fails CI for a route without it.
"""

# Toolsets an MCP client can ask for; `core` is always on.
TOOLSETS = ("core", "cases", "execution", "planning", "catalog", "admin", "consumers", "reports")


def op(operation_id: str, scope: str | None, toolset: str, mcp: bool = True) -> dict:
    if mcp and toolset not in TOOLSETS:
        raise ValueError(f"unknown toolset {toolset!r} for {operation_id}")
    return {
        "operation_id": operation_id,
        "openapi_extra": {"x-scope": scope, "x-mcp": mcp, "x-toolset": toolset},
    }


operation = op
