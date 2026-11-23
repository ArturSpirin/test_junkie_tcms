"""T5 `/mcp`: tools listed by toolset and effective scope, called in-process through the real API."""

import base64

import httpx
from fastapi.testclient import TestClient
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.api.operations import TOOLSETS
from test_junkie_tcms.auth.scopes import ALL_SCOPES
from test_junkie_tcms.mcp_server.dispatch import envelope
from test_junkie_tcms.plugins import PluginContext
from tests import support
from tests.catalog_seed import events, make_product, ok, url
from tests.execution_seed import make_case, run_seed
from tests.support import add_member, login
from tests.test_csv_io import source
from tests.test_mcp_drift import TOOL_COUNT, demo_router

ACCEPT = "application/json, text/event-stream"


def token(client, *scopes: str) -> str:
    return ok(client.post(url("/tokens"), json={"name": "agent", "scopes": list(scopes)}), 201)["token"]


def rpc(client, value: str | None, method: str, params: dict | None = None, query: str = ""):
    headers = {"Accept": ACCEPT}
    if value is not None:
        headers["Authorization"] = f"Bearer {value}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/mcp/" + query, json=body, headers=headers)


def tool_names(client, value: str, query: str = "") -> set[str]:
    response = rpc(client, value, "tools/list", query=query)
    assert response.status_code == 200, response.text
    return {tool["name"] for tool in response.json()["result"]["tools"]}


def call(client, value: str, tool: str, query: str = "", **arguments) -> dict:
    response = rpc(client, value, "tools/call", {"name": tool, "arguments": arguments}, query=query)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] == (result["structuredContent"]["status"] >= 400)
    return result["structuredContent"]


def mcp_client(app) -> TestClient:
    """A client that runs the app's lifespan, which builds the tools and starts the MCP server.

    Use it as a context manager: ``with mcp_client(self.env.app) as mcp:``.
    """
    return TestClient(app)


def make_admin_token(owner) -> str:
    return token(owner, *sorted(ALL_SCOPES))


@Suite(parameters=support.DATABASES)
class McpServer:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    # Listing

    @test()
    def test_default_toolsets_list_34_tools_and_all_lists_every_tool(self, suite_parameter):
        app = self.env.app
        with mcp_client(app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            assert len(tool_names(mcp, admin_token)) == 34
            assert len(tool_names(mcp, admin_token, "?toolsets=all")) == TOOL_COUNT
            all_but_admin = ",".join(t for t in TOOLSETS if t != "admin")
            assert len(tool_names(mcp, admin_token, f"?toolsets={all_but_admin}")) == TOOL_COUNT - 24
            assert tool_names(mcp, admin_token, "?toolsets=cases") <= tool_names(mcp, admin_token)
            app.state.settings.mcp_default_toolsets = "all"
            assert len(tool_names(mcp, admin_token)) == TOOL_COUNT

    @test()
    def test_an_unknown_toolset_is_a_400(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            admin_token = make_admin_token(self.env.owner)
            response = rpc(mcp, admin_token, "tools/list", query="?toolsets=cases,nope")
            assert response.status_code == 400 and "nope" in response.json()["detail"]

    @test()
    def test_tools_carry_the_mapped_header_args(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            admin_token = make_admin_token(self.env.owner)
            tools = {t["name"]: t for t in rpc(mcp, admin_token, "tools/list").json()["result"]["tools"]}
            update = tools["cases_update"]["inputSchema"]
            assert "expected_version" in update["required"] and "If-Match" not in update["properties"]
            assert "idempotency_key" in tools["cases_create"]["inputSchema"]["properties"]
            assert tools["cases_list"]["annotations"]["readOnlyHint"] is True

    @test()
    def test_tools_follow_role_and_token_scopes(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            member = add_member(owner, "eddie@example.com", "editor")
            eddie = self.env.client()
            login(eddie, "eddie@example.com")
            value = token(eddie, "read", "write:cases")
            assert {"cases_create", "cases_list"} <= tool_names(mcp, value)
            assert "results_create" not in tool_names(mcp, value)  # the editor role has it, the token doesn't
            ok(owner.patch(f"/api/v1/orgs/acme/members/{member['user_id']}", json={"role": "viewer"}))
            names = tool_names(mcp, value)
            assert "cases_list" in names and "cases_create" not in names  # the token still says write:cases
            refused = call(mcp, value, "cases_create", org="acme", product="x", feature_id="y", title="t")
            assert refused["status"] == 403 and refused["error"]["detail"] == "Needs scope write:cases"

    # Refusals: a tool hidden by scope or toolset says why; only a name that isn't a tool is unknown

    @test()
    def test_a_tool_hidden_by_scope_is_a_403_naming_the_scope(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            cc = run_seed(owner)["cycle_case"]["id"]
            read_only = token(owner, "read")
            refused = call(mcp, read_only, "results_create", org="acme", id=cc, status="success")
            assert refused["status"] == 403 and refused["error"]["status"] == 403
            assert refused["error"]["detail"] == "Needs scope write:execution"
            execution = token(owner, "read", "write:execution")
            refused = call(mcp, execution, "cases_update", org="acme", case="PAY-1", expected_version=1)
            assert refused["status"] == 403 and refused["error"]["detail"] == "Needs scope write:cases"
            # scope comes before toolset: the admin toolset is off here, but the missing scope is what blocks
            stats = call(mcp, read_only, "mcp_usage", org="acme")
            assert stats["status"] == 403 and stats["error"]["detail"] == "Needs scope admin or audit:read"

    @test()
    def test_a_tool_hidden_by_toolset_is_a_403_naming_the_toolset(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            cycle = run_seed(owner)["cycle"]["id"]
            refused = call(mcp, admin_token, "reports_cycle", org="acme", cycle_id=cycle)
            assert refused["status"] == 403 and refused["error"]["detail"] == (
                "reports_cycle is in toolset reports: connect with ?toolsets=reports or ?toolsets=all"
            )
            for query in ("?toolsets=reports", "?toolsets=all"):
                report = call(mcp, admin_token, "reports_cycle", query=query, org="acme", cycle_id=cycle)
                assert report["status"] == 200, (query, report)

    @test()
    def test_a_name_that_is_not_a_tool_is_a_404(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            admin_token = make_admin_token(self.env.owner)
            for query in ("", "?toolsets=all"):
                unknown = call(mcp, admin_token, "nope_tool", query=query)
                assert unknown["status"] == 404 and unknown["error"]["detail"] == "Unknown tool nope_tool"

    # Auth

    @test()
    def test_no_or_bad_bearer_is_a_401(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            for value in (None, "nope"):
                response = rpc(mcp, value, "tools/list")
                assert response.status_code == 401 and response.headers["WWW-Authenticate"] == "Bearer"

    @test()
    def test_a_consumer_token_is_a_403(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            anon = self.env.client()
            pairing = ok(anon.post("/api/v1/pair"), 201)
            approval = {
                "user_code": pairing["user_code"],
                "name": "box",
                "product_ids": [make_product(owner)["id"]],
            }
            ok(owner.post(url("/pair/approve"), json=approval), 201)
            consumer = ok(anon.post("/api/v1/pair/token", json={"device_code": pairing["device_code"]}))[
                "access_token"
            ]
            assert rpc(mcp, consumer, "tools/list").status_code == 403

    @test()
    def test_mcp_needs_the_lifespan(self, suite_parameter):
        app = self.env.app
        admin_token = make_admin_token(self.env.owner)
        assert rpc(TestClient(app), admin_token, "tools/list").status_code == 503

    # Calls

    @test()
    def test_a_stale_expected_version_is_a_409(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            case = run_seed(owner)["case"]
            args = {"org": "acme", "case": case["key"]}
            version = case["current_version"]
            fresh = call(
                mcp, admin_token, "cases_update", **args, expected_version=version, title="Pay by card v2"
            )
            assert fresh["status"] == 200 and fresh["data"]["title"] == "Pay by card v2"
            assert fresh["data"]["current_version"] == version + 1 and fresh["etag"] == f'"{version + 1}"'
            stale = call(mcp, admin_token, "cases_update", **args, expected_version=version, title="Lost")
            assert stale["status"] == 409 and stale["error"]["current_version"] == version + 1

    @test()
    def test_an_idempotency_key_replays_even_with_the_args_reordered(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            s = run_seed(owner)
            first = call(
                mcp,
                admin_token,
                "cases_create",
                org="acme",
                product=s["product"]["id"],
                feature_id=s["child"]["id"],
                title="Refund",
                priority="high",
                idempotency_key="k-1",
            )
            assert first["status"] == 201 and "replayed" not in first
            again = call(
                mcp,
                admin_token,
                "cases_create",
                idempotency_key="k-1",
                priority="high",
                title="Refund",
                feature_id=s["child"]["id"],
                product=s["product"]["id"],
                org="acme",
            )
            assert (
                again["status"] == 201
                and again["replayed"] is True
                and again["data"]["id"] == first["data"]["id"]
            )
            other = call(
                mcp,
                admin_token,
                "cases_create",
                org="acme",
                product=s["product"]["id"],
                feature_id=s["child"]["id"],
                title="Other",
                idempotency_key="k-1",
            )
            assert other["status"] == 422

    @test()
    def test_a_title_of_only_spaces_is_a_422(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            s = run_seed(owner)
            p, f, case = s["product"]["id"], s["child"]["id"], s["case"]
            args = {"org": "acme", "product": p, "feature_id": f}
            assert call(mcp, admin_token, "cases_create", **args, title="   ")["status"] == 422
            update = {"org": "acme", "case": case["key"], "expected_version": case["current_version"]}
            assert call(mcp, admin_token, "cases_update", **update, title=" \t ")["status"] == 422
            stripped = call(mcp, admin_token, "cases_create", **args, title=" Refund ")
            assert stripped["status"] == 201 and stripped["data"]["title"] == "Refund"

    @test()
    def test_a_name_of_only_spaces_is_a_422_and_spaces_around_one_are_stripped(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            s = run_seed(owner)
            at = {"org": "acme", "product": s["product"]["id"]}
            tools = [
                ("products_create", {"org": "acme", "key": "NEW"}),
                ("features_create", at),
                ("plans_create", at),
                ("cycles_create", at),
            ]
            for tool, args in tools:
                blank = call(mcp, admin_token, tool, "?toolsets=all", **args, name=" \t ")
                assert blank["status"] == 422, (tool, blank)
                made = call(mcp, admin_token, tool, "?toolsets=all", **args, name="  Nightly ")
                assert made["status"] == 201 and made["data"]["name"] == "Nightly", (tool, made)

    @test()
    def test_missing_and_unknown_args_are_a_422(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            admin_token = make_admin_token(self.env.owner)
            missing = call(mcp, admin_token, "cases_update", org="acme", case="PAY-1", title="x")
            assert missing["status"] == 422 and "expected_version" in missing["error"]["detail"]
            unknown = call(mcp, admin_token, "me_get", bogus=1)
            assert unknown["status"] == 422 and "bogus" in unknown["error"]["detail"]

    @test()
    def test_a_result_over_mcp_is_recorded_and_audited_as_mcp(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            cc = run_seed(owner)["cycle_case"]["id"]
            result = call(mcp, admin_token, "results_create", org="acme", id=cc, status="success")
            assert result["status"] == 201 and result["data"]["via"] == "mcp"
            [event] = [e for e in events(owner, "result") if e["entity_id"] == result["data"]["id"]]
            assert event["via"] == "mcp"
            audited = ok(owner.get(url("/audit"), params={"entity_type": "result", "via": "mcp"}))["items"]
            assert [e["entity_id"] for e in audited] == [result["data"]["id"]]

    @test()
    def test_cycle_cases_add_takes_a_key_or_an_id(self, suite_parameter):
        self.env.app.state.settings.mcp_default_toolsets = "all"
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            s = run_seed(owner)
            p, cycle = s["product"]["id"], s["cycle"]["id"]
            second = make_case(owner, p, s["child"]["id"], "Second")
            third = make_case(owner, p, s["child"]["id"], "Third")
            args = {"org": "acme", "id": cycle}
            by_key = call(mcp, admin_token, "cycle_cases_add", **args, case_ids=["PAY-2", "PAY-1"])
            assert by_key["status"] == 200, by_key
            assert by_key["data"] == {"added": [second["id"]], "already_present": [s["case"]["id"]]}
            by_id = call(mcp, admin_token, "cycle_cases_add", **args, case_ids=[third["id"]])
            assert by_id["data"] == {"added": [third["id"]], "already_present": []}
            unknown = call(mcp, admin_token, "cycle_cases_add", **args, case_ids=["PAY-99"])
            assert unknown["status"] == 422
            assert unknown["error"]["detail"] == "case_id PAY-99 is not a case of this product"

    @test()
    def test_an_ext_router_is_served_over_mcp(self, suite_parameter):
        app = self.env.app
        owner = self.env.owner
        PluginContext(app, "demo").add_router(demo_router())
        value = token(owner, "read")
        with TestClient(app) as mcp:
            assert "demo_greet" in tool_names(mcp, value)
            greeted = call(mcp, value, "demo_greet", name="Ada")
        assert greeted == {"status": 200, "data": {"hello": "Ada", "via": "mcp"}}

    # Envelope

    @test()
    def test_envelope_keeps_json_text_and_empty_and_wraps_binary(self, suite_parameter):
        assert envelope(httpx.Response(204)) == {"status": 204, "data": None}
        assert envelope(httpx.Response(200, json={"a": 1})) == {"status": 200, "data": {"a": 1}}
        csv_body = httpx.Response(
            200, content=b"key\nPAY-1\n", headers={"content-type": "text/csv; charset=utf-8"}
        )
        assert envelope(csv_body) == {"status": 200, "data": "key\nPAY-1\n"}
        zipped = httpx.Response(200, content=b"PK\x03\x04\xff", headers={"content-type": "application/zip"})
        assert envelope(zipped) == {
            "status": 200,
            "data": {
                "content_type": "application/zip",
                "base64": base64.b64encode(b"PK\x03\x04\xff").decode(),
            },
        }

    @test()
    def test_exports_over_mcp_and_a_bundle_imports_back(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            p = source(owner)["product"]["id"]
            text = call(mcp, admin_token, "exports_create", org="acme", product=p, format="csv")
            assert text["status"] == 200 and text["data"].startswith("key,version,feature,title,")
            zipped = call(mcp, admin_token, "exports_create", org="acme", product=p, format="md-bundle")
            assert zipped["status"] == 200 and zipped["data"]["content_type"] == "application/zip"
            back = call(
                mcp,
                admin_token,
                "imports_create",
                org="acme",
                product=p,
                format="md-bundle",
                bundle=zipped["data"]["base64"],
            )
            assert back["status"] == 200, back
            assert (back["data"]["created"], back["data"]["unchanged"]) == (0, 2)
