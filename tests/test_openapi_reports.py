"""T6's contract: every report, search and CSV operation carries its scope, toolset and MCP flag."""

import pytest
from test_openapi_cases import ops

T6_OPS = {
    "reports_release": ("read", "reports", True),
    "reports_product": ("read", "reports", True),
    "reports_org": ("read", "reports", True),
    "reports_feature": ("read", "reports", True),
    "reports_cycle": ("read", "reports", True),
    "search": ("read", "cases", True),
    "exports_create": ("read", "cases", True),
    "imports_create": ("write:cases", "cases", True),
}


@pytest.fixture
def spec(client_factory):
    response = client_factory().get("/api/v1/openapi.json")
    assert response.status_code == 200
    return response.json()["paths"]


@pytest.mark.parametrize("name", sorted(T6_OPS))
def test_t6_operation_is_marked(spec, name):
    op = ops(spec)[name]
    assert (op["x-scope"], op["x-toolset"], op["x-mcp"]) == T6_OPS[name]


def test_import_body_keeps_room_for_mapping(client_factory):
    schemas = client_factory().get("/api/v1/openapi.json").json()["components"]["schemas"]
    assert "mapping" in schemas["ImportIn"]["properties"]
    assert "mapping" not in schemas["ImportIn"].get("required", [])
