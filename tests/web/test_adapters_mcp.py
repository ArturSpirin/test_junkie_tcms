"""The MCP page adapter, run in node against a live server: each range's state and mapped shape (KPIs, chart
columns, tools, clients, the updates feed and the last call), the tool detail drawer, the live poll, and a raw
error. The page makes no writes; its calls are made through the live server's /mcp endpoint."""

import json
from datetime import UTC, datetime

import httpx
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.web.live import LiveServer, as_sent, body_of, run_js

ORG = "/api/v1/orgs/acme"
ACCEPT = "application/json, text/event-stream"


@Suite(parameters=support.DATABASES)
class WebMcpAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def token(self) -> str:
        response = self.live.owner.post(
            f"{ORG}/tokens", json={"name": "agent", "scopes": ["admin", "read", "write:catalog"]}
        )
        assert response.status_code == 201, response.text
        return response.json()["token"]

    def call(self, value: str, tool: str, **arguments) -> dict:
        """One tools/call on the live server's /mcp; returns the result's structuredContent."""
        params = {"name": tool, "arguments": arguments}
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
        headers = {"Accept": ACCEPT, "Authorization": f"Bearer {value}"}
        with httpx.Client(base_url=self.live.url, timeout=30) as client:
            response = client.post("/mcp/?toolsets=all", json=body, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["result"]["structuredContent"]

    def seed_calls(self) -> None:
        """Two reads, one 404 and one write, in that order."""
        value = self.token()
        for _ in range(2):
            assert self.call(value, "me_get")["status"] == 200
        assert self.call(value, "orgs_get", org="nope")["status"] == 404
        made = self.call(value, "products_create", org="acme", key="PAY", name="Payments")
        assert made["status"] == 201, made

    def load(self, params):
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps(params)};
            const ctx = await h.ctx(params);
            return await (await h.adapter("mcp")).load(params, ctx);""",
            "/app?view=mcp",
        )

    @test()
    def test_no_calls_today_is_the_empty_state_with_the_tool_list_and_feed(self, suite_parameter):
        out = self.load({})
        assert out["state"] == "empty"
        d = out["data"]
        server = self.live.owner.get(f"{ORG}/mcp/server").json()
        assert d["server"] == {"up": True, "version": server["version"]}
        assert d["ranges"]["today"]["totals"] == {"calls": 0, "errors": 0, "tokens": 0, "clients": 0}
        assert len(d["tools"]) == server["tool_count"] and d["apiOps"] >= server["tool_count"]
        by_name = {t["name"]: t for t in d["tools"]}
        kinds = {n: by_name[n]["kind"] for n in ("cases_list", "cases_create", "cases_archive")}
        assert kinds == {"cases_list": "r", "cases_create": "i", "cases_archive": "d"}
        listed = {i["name"]: i for i in self.live.owner.get(f"{ORG}/mcp/tools").json()["items"]}
        assert by_name["cases_list"]["desc"] == listed["cases_list"]["description"]
        assert by_name["cases_list"]["tokDef"] == listed["cases_list"]["def_tokens"]
        assert by_name["cases_list"]["tokCall"] is None and by_name["cases_list"]["calls"] == {"today": 0}
        assert d["toolsets"][-1] == "admin" and set(d["toolsets"]) == {t["toolset"] for t in d["tools"]}
        assert d["lastCall"] is None and d["errorsMostly"] is None and d["clientNames"] == []
        # the server's start wrote the feed's first row
        assert d["updates"][0]["kind"] == "acc"
        assert d["updates"][0]["title"] == f"Server v{server['version']} started"
        # only today's range is "empty": a longer one with no calls still draws its chart
        week = self.load({"ui": "7d"})
        assert week["state"] == "7d" and len(week["data"]["ranges"]["7d"]["columns"]) == 7

    @test()
    def test_today_maps_kpis_chart_tools_clients_and_last_call(self, suite_parameter):
        self.seed_calls()
        out = self.load({})
        assert out["state"] == "today"
        d = out["data"]
        today = d["ranges"]["today"]
        assert {k: today["totals"][k] for k in ("calls", "errors", "clients")} == {
            "calls": 4,
            "errors": 1,
            "clients": 1,
        }
        usage = self.live.owner.get(f"{ORG}/mcp/usage", params={"bucket": "hour"}).json()["items"]
        assert today["totals"]["tokens"] == round(sum(b["resp_bytes"] for b in usage) / 4)
        assert len(today["columns"]) == 24
        now = today["columns"][today["now"]]
        assert now["reads"] + now["writes"] == 4 and now["errors"] == 1
        assert all(c.get("later") for c in today["columns"][today["now"] + 1 :])
        by_name = {t["name"]: t for t in d["tools"]}
        assert by_name["me_get"]["calls"] == {"today": 2} and by_name["me_get"]["tokCall"] > 0
        assert (by_name["orgs_get"]["calls"], by_name["orgs_get"]["errors"]) == ({"today": 1}, 1)
        assert d["errorsMostly"] == "404"
        [client] = self.live.owner.get(f"{ORG}/mcp/clients").json()["items"]
        assert d["clientNames"] == [client["name"]]
        last = d["lastCall"]
        assert (last["call"], last["code"], last["at"]) == ("products_create", 201, "just now")
        caller = (last["agent"], last["kind"], last["actorId"])
        assert caller == (client["name"], client["kind"], client["actor_id"])
        assert last["ms"] >= 0 and last["tokens"] >= 0
        start, end = (datetime.fromisoformat(d["live"][k]) for k in ("nowStart", "nowEnd"))
        assert start <= datetime.now(UTC) < end

    @test()
    def test_ranges_and_picker_states_come_from_the_hash_and_query(self, suite_parameter):
        self.seed_calls()
        for ui, n in (("7d", 7), ("14d", 14), ("30d", 30)):
            out = self.load({"ui": ui})
            assert out["state"] == ui and out["data"]["range"] == ui
            r = out["data"]["ranges"][ui]
            assert len(r["columns"]) == n and r["now"] == n - 1 and r["totals"]["calls"] == 4
            assert out["data"]["live"] is not None
        day = datetime.now().strftime("%Y-%m-%d")
        custom = self.load({"ui": "custom-applied", "from": day, "to": day})
        assert custom["state"] == "custom-applied" and custom["data"]["range"] == "custom"
        assert custom["data"]["picker"] == {"value": "custom", "applied": True, "from": day, "to": day}
        assert custom["data"]["ranges"]["custom"]["totals"]["calls"] == 4
        assert custom["data"]["ranges"]["custom"]["now"] == -1 and custom["data"]["live"] is None
        opened = self.load({"ui": "custom-open"})
        assert opened["state"] == "custom-open"
        assert opened["data"]["picker"] == {"value": "custom", "open": True}
        assert self.load({"ui": "today-hover"})["state"] == "today-hover"

    @test()
    def test_tool_detail_maps_operation_args_and_recent_calls(self, suite_parameter):
        self.seed_calls()
        out = self.load({"id": "orgs_get"})
        assert out["state"] == "tool-detail"
        x = out["data"]["detail"]
        shown = (x["tool"], x["path"], x["errorsToday"], x["audited"])
        assert shown == ("orgs_get", "/api/v1/orgs/{org}", 1, False)
        assert {"arg": "org", "where": "path", "type": "string", "required": True, "note": ""} in [
            {**p, "note": ""} for p in x["params"]
        ]
        [c] = x["calls"]
        assert (c["call"], c["code"]) == ("orgs_get", 404)
        write = self.load({"id": "products_create"})["data"]["detail"]
        assert write["audited"] is True and write["path"] == "/api/v1/orgs/{org}/products"
        assert {"key", "name"} <= {p["arg"] for p in write["params"] if p["where"] == "body"}
        assert [c["code"] for c in write["calls"]] == [201]

    @test()
    def test_live_poll_reads_usage_clients_and_the_last_call(self, suite_parameter):
        self.seed_calls()
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx({});
            const mcp = await h.adapter("mcp");
            const { data } = await mcp.load({}, ctx);
            const before = h.calls.length;
            const p = await mcp.poll(data.live, ctx);
            return { p, asked: h.calls.slice(before).map((c) => c.path) };""",
            "/app?view=mcp",
        )
        p = out["p"]
        assert p["calls"] == 4 and p["now"]["errors"] == 1 and p["now"]["reads"] + p["now"]["writes"] == 4
        [client] = self.live.owner.get(f"{ORG}/mcp/clients").json()["items"]
        assert p["clients"] == [client["name"]]
        assert (p["lastCall"]["call"], p["lastCall"]["at"]) == ("products_create", "just now")
        assert f"{ORG}/mcp/calls?limit=1" in out["asked"]
        assert sum("/mcp/usage?" in a and "bucket=hour" in a for a in out["asked"]) == 1
        assert sum("/mcp/clients?" in a for a in out["asked"]) == 1

    @test()
    def test_a_range_over_90_days_is_the_raw_422(self, suite_parameter):
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx({});
            const params = { ui: "custom-applied", from: "2026-01-01", to: "2026-11-01" };
            return h.fail((await h.adapter("mcp")).load(params, ctx));""",
            "/app?view=mcp",
        )
        asked = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx({});
            const params = { ui: "custom-applied", from: "2026-01-01", to: "2026-11-01" };
            try { await (await h.adapter("mcp")).load(params, ctx); } catch (e) { /* the same 422 */ }
            return h.calls.map((c) => c.path).filter((p) => p.includes("/mcp/tools?"));""",
            "/app?view=mcp",
        )
        [path] = asked
        query = dict(httpx.URL(path).params)
        texts = {
            p: as_sent(self.live.owner.get(f"{ORG}/mcp/{p}", params={**query, **extra}))
            for p, extra in (("tools", {}), ("usage", {"bucket": "hour"}), ("clients", {}))
        }
        assert out["name"] == "ApiError" and out["status"] == 422
        assert all(body_of(t)["status"] == 422 for t in texts.values())
        assert out["raw"] in texts.values()

    @test()
    def test_an_unknown_tool_is_an_error(self, suite_parameter):
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx({});
            return h.fail((await h.adapter("mcp")).load({ id: "no_such_tool" }, ctx));""",
            "/app?view=mcp",
        )
        assert out == {"name": "Error", "status": None, "raw": "Error: No MCP tool is named no_such_tool."}
