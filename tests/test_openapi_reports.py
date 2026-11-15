"""T6's contract: every report, search and CSV operation carries its scope, toolset and MCP flag."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.test_openapi_cases import ops

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


def spec(env):
    response = env.client().get("/api/v1/openapi.json")
    assert response.status_code == 200
    return response.json()["paths"]


@Suite(parameters=support.DATABASES)
class OpenapiReports:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    @test(parameters=sorted(T6_OPS))
    def test_t6_operation_is_marked(self, suite_parameter, parameter):
        name = parameter
        op = ops(spec(self.env))[name]
        assert (op["x-scope"], op["x-toolset"], op["x-mcp"]) == T6_OPS[name]

    @test()
    def test_import_body_keeps_room_for_mapping(self, suite_parameter):
        schemas = self.env.client().get("/api/v1/openapi.json").json()["components"]["schemas"]
        assert "mapping" in schemas["ImportIn"]["properties"]
        assert "mapping" not in schemas["ImportIn"].get("required", [])
