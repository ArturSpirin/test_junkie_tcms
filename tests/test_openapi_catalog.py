"""Every catalog operation is in the one OpenAPI contract with the marks T5 builds MCP tools from."""

import pytest
from catalog_seed import OPERATION_NAMES

PLANNING = {name for name in OPERATION_NAMES if name.startswith("plans_")}


@pytest.fixture
def spec(client_factory):
    response = client_factory().get("/api/v1/openapi.json")
    assert response.status_code == 200
    return {
        op["operationId"]: op
        for path in response.json()["paths"].values()
        for op in path.values()
        if isinstance(op, dict) and "operationId" in op
    }


@pytest.mark.parametrize("name", OPERATION_NAMES)
def test_operation_is_marked(spec, name):
    op = spec[name]
    reads = name.endswith(("_list", "_get"))
    expected = "read" if reads else "write:planning" if name in PLANNING else "write:catalog"
    assert op["x-scope"] == expected
    assert op["x-toolset"] == ("planning" if name in PLANNING else "catalog")
    assert op["x-mcp"] is True
    assert any(p["name"] == "rich" for p in op.get("parameters", []))
