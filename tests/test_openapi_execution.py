"""T4's contract: every cycle, result and attachment operation carries its scope, toolset and MCP flag."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.test_openapi_cases import ops

EXECUTION_OPS = {
    "cycles_list": ("read", "execution", True),
    "cycles_create": ("write:planning", "planning", True),
    "cycles_preview": ("read", "planning", True),
    "cycles_get": ("read", "execution", True),
    "cycles_update": ("write:planning", "planning", True),
    "cycles_close": ("write:planning", "planning", True),
    "cycles_reopen": ("write:planning", "planning", True),
    "cycle_cases_add": ("write:planning", "planning", True),
    "cycle_cases_assign": ("write:planning", "planning", True),
    "cycle_cases_refresh_version": ("write:planning", "planning", True),
    "cycles_bulk_create": ("write:planning", "planning", True),
    "cycle_batches_get": ("read", "planning", True),
    "cycle_cases_list": ("read", "execution", True),
    "results_create": ("write:execution", "execution", True),
    "results_list": ("read", "execution", True),
    "results_bulk_create": ("write:execution", "execution", True),
    "attachments_upload": ("write:execution", "execution", False),
    "attachments_upload_base64": ("write:execution", "execution", True),
    "attachments_download": ("read", "execution", False),
}


def spec(env):
    response = env.client().get("/api/v1/openapi.json")
    assert response.status_code == 200
    return response.json()["paths"]


@Suite(parameters=support.DATABASES)
class OpenapiExecution:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    @test(parameters=sorted(EXECUTION_OPS))
    def test_execution_operation_is_marked(self, suite_parameter, parameter):
        name = parameter
        op = ops(spec(self.env))[name]
        assert (op["x-scope"], op["x-toolset"], op["x-mcp"]) == EXECUTION_OPS[name]

    @test()
    def test_results_have_no_edit_or_delete(self, suite_parameter):
        names = set(ops(spec(self.env)))
        assert not {
            n for n in names if n.startswith("results_") and n.split("_", 1)[1] in ("update", "delete")
        }
