"""Route metadata the MCP generator (T5) reads: operationId, scope, toolset and whether it is a tool."""


def op(operation_id: str, scope: str | None, toolset: str, mcp: bool = True) -> dict:
    return {
        "operation_id": operation_id,
        "openapi_extra": {"x-scope": scope, "x-mcp": mcp, "x-toolset": toolset},
    }
