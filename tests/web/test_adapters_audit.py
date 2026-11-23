"""Web adapter for the Audit log, run in node against a live server: each data-driven state, the mapped event
(request id and MCP tool included), the filters sent to the server, the export read, and a raw error."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_feature, ok, url
from tests.execution_seed import make_case, run_seed
from tests.test_mcp_server import call, make_admin_token, mcp_client
from tests.web.live import LiveServer, as_sent, body_of, run_js


@Suite(parameters=support.DATABASES)
class WebAuditAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def load(self, params):
        """The adapter's { state, data, asked } for params, signed in as the acme owner, with the shell's
        context; asked is every audit_list path the adapter called."""
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps(params)};
            const ctx = await h.ctx(params);
            const out = await (await h.adapter("audit")).load(params, ctx);
            out.asked = h.calls.map((c) => c.path).filter((p) => p.includes("/audit?"));
            return out;""",
            "/app?view=audit",
        )

    def product(self, key="PAY"):
        """Create a product; returns (ProductOut, the request id its audit row carries)."""
        response = self.live.owner.post(url("/products"), json={"key": key, "name": f"{key} product"})
        assert response.status_code == 201, response.text
        return response.json(), response.headers["x-request-id"]

    def rows(self, **params):
        return ok(self.live.owner.get(url("/audit"), params={"limit": 200, **params}))["items"]

    @test()
    def test_default_maps_each_row_with_its_request_id(self, suite_parameter):
        product, request_id = self.product()
        out = self.load({})
        assert out["state"] == "default"
        data = out["data"]
        [row] = [e for e in data["events"] if e["entityId"] == product["id"]]
        [api] = self.rows(entity_id=product["id"])
        assert (row["eid"], row["action"], row["type"], row["via"]) == (
            api["id"],
            "product.create",
            "product",
            api["via"],
        )
        assert row["actor"] == {"kind": "person", "id": api["actor_id"], "name": "Olive Owner"}
        assert (row["detail"]["requestId"], row["detail"]["tool"]) == (request_id, "")
        assert row["raw"] == api
        assert data["total"] == len(self.rows()) and data["open"] == -1
        assert data["retention"]["days"] == 90 and data["retention"]["oldest"]
        assert data["filter"]["range"] == {"value": "7d"}
        assert all("since=" in p and "limit=50" in p for p in out["asked"])

    @test()
    def test_mcp_row_carries_its_tool_and_q_finds_it(self, suite_parameter):
        owner = self.live.owner
        with mcp_client(self.live.env.app) as mcp:
            cc = run_seed(owner)["cycle_case"]["id"]
            call(mcp, make_admin_token(owner), "results_create", org="acme", id=cc, status="success")
        [api] = self.rows(q="results_create")
        out = self.load({"q": "results_create"})
        assert out["state"] == "filtered-agent"
        [row] = out["data"]["events"]
        assert (row["eid"], row["via"], row["detail"]["tool"]) == (api["id"], "mcp", "results_create")
        assert row["detail"]["requestId"] == api["request_id"] and api["request_id"].startswith("req_")
        assert any("q=results_create" in p for p in out["asked"])

    @test()
    def test_filters_go_to_the_server(self, suite_parameter):
        self.product("PAY")
        self.product("ID")
        out = self.load({"action": "product.create", "via": "ui", "actor": "person"})
        assert out["state"] == "filtered-agent"
        assert {e["action"] for e in out["data"]["events"]} == {"product.create"}
        assert len(out["data"]["events"]) == 2
        [asked] = out["asked"]
        assert "action=product.create" in asked and "via=ui" in asked and "actor_kind=user" in asked
        assert self.load({"ui": "filter-open"})["state"] == "filter-open"

    @test()
    def test_no_match_is_the_empty_state(self, suite_parameter):
        self.product()
        out = self.load({"action": "nothing.here"})
        assert out["state"] == "empty"
        assert out["data"]["events"] == [] and out["data"]["total"] == 0

    @test()
    def test_open_expands_one_event(self, suite_parameter):
        product, _ = self.product()
        [api] = self.rows(entity_id=product["id"])
        out = self.load({"open": api["id"]})
        assert out["state"] == "expanded"
        assert out["data"]["events"][out["data"]["open"]]["eid"] == api["id"]

    @test()
    def test_one_case_is_the_entity_state_with_its_key(self, suite_parameter):
        product, _ = self.product()
        feature = make_feature(self.live.owner, product["id"], "Checkout")
        case = make_case(self.live.owner, product["id"], feature["id"], "Pay by card")
        out = self.load({"type": "case", "entity": case["id"]})
        assert out["state"] == "entity"
        data = out["data"]
        key = case["key"]
        assert data["entity"] == {"type": "case", "id": key, "key": key, "title": "Pay by card"}
        assert [(e["action"], e["type"], e["id"]) for e in data["events"]] == [("case.create", "case", key)]
        assert data["filter"]["entityLabel"] == case["key"] and data["filter"]["range"] == {"value": "30d"}
        assert any("entity_type=test_case" in p and f"entity_id={case['id']}" in p for p in out["asked"])

    @test()
    def test_a_period_before_the_oldest_row_is_the_retention_state(self, suite_parameter):
        self.product()
        out = self.load({"range": "custom", "from": "2020-01-01"})
        assert out["state"] == "retention"
        assert out["data"]["filter"]["range"]["from"] == "2020-01-01"
        assert out["data"]["events"]

    @test()
    def test_export_reads_every_matching_row(self, suite_parameter):
        self.product("PAY")
        self.product("ID")
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx();
            return await (await h.adapter("audit")).actions.export({ action: "product.create" }, ctx);""",
            "/app?view=audit",
        )
        assert sorted(r["id"] for r in out) == sorted(r["id"] for r in self.rows(action="product.create"))
        assert len(out) == 2

    @test()
    def test_a_bad_filter_is_the_raw_422(self, suite_parameter):
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx();
            return h.fail((await h.adapter("audit")).load({ via: "fax" }, ctx));""",
            "/app?view=audit",
        )
        raw = as_sent(self.live.owner.get(url("/audit"), params={"via": "fax"}))
        assert body_of(raw)["status"] == 422
        assert out == {"name": "ApiError", "status": 422, "raw": raw}
