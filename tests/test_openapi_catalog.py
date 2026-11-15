"""Every catalog operation is in the one OpenAPI contract with the marks T5 builds MCP tools from."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import OPERATION_NAMES

PLANNING = {name for name in OPERATION_NAMES if name.startswith("plans_")}


@Suite(parameters=support.DATABASES)
class OpenapiCatalog:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def spec(self):
        response = self.env.client().get("/api/v1/openapi.json")
        assert response.status_code == 200
        return {
            op["operationId"]: op
            for path in response.json()["paths"].values()
            for op in path.values()
            if isinstance(op, dict) and "operationId" in op
        }

    @test(parameters=OPERATION_NAMES)
    def test_operation_is_marked(self, suite_parameter, parameter):
        spec, name = self.spec(), parameter
        op = spec[name]
        reads = name.endswith(("_list", "_get"))
        expected = "read" if reads else "write:planning" if name in PLANNING else "write:catalog"
        assert op["x-scope"] == expected
        assert op["x-toolset"] == ("planning" if name in PLANNING else "catalog")
        assert op["x-mcp"] is True
        assert any(p["name"] == "rich" for p in op.get("parameters", []))
