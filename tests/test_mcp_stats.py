"""Per-tool MCP stats recorded on each `/mcp` call, and the three MCP page operations."""

import dataclasses
import json
import math
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

import anyio
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms import __version__
from test_junkie_tcms.db.models import Actor, McpServerEvent, McpToolCall, McpToolStat
from test_junkie_tcms.mcp_server import events, server, stats
from test_junkie_tcms.mcp_server.generator import build_tools, tool_list_hash
from tests import support
from tests.catalog_seed import ok, url
from tests.support import add_member, login
from tests.test_mcp_server import call, rpc, token, tool_names

T0 = datetime(2026, 11, 14, 10, 15, tzinfo=UTC)
MCP_OPS = {"mcp_tools_list", "mcp_usage", "mcp_server_get", "mcp_clients", "mcp_updates", "mcp_calls"}
TOOL_COUNT = 95


def make_clock(env):
    """`stats.now()` at a set time; move it with `clock[0] = ...`."""
    at = [T0]
    env.patch(stats, "now", lambda: at[0])
    return at


def rows(app) -> list[McpToolStat]:
    with app.state.sessionmaker() as db:
        return list(db.scalars(select(McpToolStat).order_by(McpToolStat.tool, McpToolStat.hour)))


def call_all(client, value: str, tool: str, **arguments) -> dict:
    """`tools/call` with every toolset on, so the admin toolset's tools are there too."""
    params = {"name": tool, "arguments": arguments}
    response = rpc(client, value, "tools/call", params, query="?toolsets=all")
    assert response.status_code == 200, response.text
    return response.json()["result"]


def raw_call(client, value: str, tool: str, **arguments) -> int:
    """Call a tool and return the byte size of the text content `call_tool` records."""
    return len(call_all(client, value, tool, **arguments)["content"][0]["text"].encode())


@Suite(parameters=support.DATABASES)
class McpStats:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)
        self.stack = ExitStack()

    @afterTest()
    def close_env(self):
        try:
            self.stack.close()
        finally:
            self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def mcp(self):
        """A client that runs the app's lifespan (the old `mcp` fixture), exited before the Env closes."""
        return self.stack.enter_context(TestClient(self.env.app))

    # Criterion 2: recording

    @test()
    def test_each_call_adds_to_its_hours_row(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        clock = make_clock(self.env)
        sizes = [raw_call(mcp, admin_token, "me_get") for _ in range(2)]
        assert call(mcp, admin_token, "orgs_get", org="nope")["status"] >= 400
        clock[0] = T0 + timedelta(hours=1)
        raw_call(mcp, admin_token, "me_get")
        me, me_next, org = rows(app)
        assert (me.tool, me.calls, me.errors, me.resp_bytes_sum) == ("me_get", 2, 0, sum(sizes))
        assert me.hour.replace(tzinfo=UTC) == datetime(2026, 11, 14, 10, tzinfo=UTC)
        assert sum(me.resp_bytes_hist) == 2 and me.resp_bytes_hist[stats.bucket_of(sizes[0])] >= 1
        assert me_next.calls == 1 and me_next.hour.replace(tzinfo=UTC) == datetime(
            2026, 11, 14, 11, tzinfo=UTC
        )
        assert (org.tool, org.calls, org.errors) == ("orgs_get", 1, 1)
        assert me.actor_id == org.actor_id

    @test()
    def test_an_unknown_or_hidden_tool_is_not_recorded(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        owner = self.env.owner
        value = token(owner, "read")
        for name in ("nope", "mcp_usage"):
            assert call_all(mcp, value, name, org="acme")["structuredContent"]["status"] == 404
        assert rows(app) == []

    @test()
    def test_each_actor_gets_its_own_row(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        owner = self.env.owner
        add_member(owner, "eddie@example.com", "admin")
        eddie = self.env.client()
        login(eddie, "eddie@example.com")
        for value in (token(owner, "read"), token(eddie, "read")):
            raw_call(mcp, value, "me_get")
        first, second = rows(app)
        assert first.calls == second.calls == 1 and first.actor_id != second.actor_id

    @test()
    def test_a_concurrent_insert_of_the_same_row_is_retried(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        make_clock(self.env)
        real_find = stats._find
        raced = []

        def find_after_a_racer(db, org_id, tool, actor_id, hour):
            if not raced:  # another call inserts this hour's row between our select and insert
                raced.append(True)
                stats.record(app.state.sessionmaker, org_id, actor_id, tool, 200, 10, 0)
                return None
            return real_find(db, org_id, tool, actor_id, hour)

        self.env.patch(stats, "_find", find_after_a_racer)
        raw_call(mcp, admin_token, "me_get")
        [row] = rows(app)
        assert row.calls == 2

    @test()
    def test_a_failing_record_still_returns_the_result(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")

        def boom(*args):
            raise RuntimeError("db down")

        self.env.patch(stats, "record", boom)
        assert call(mcp, admin_token, "me_get")["status"] == 200
        assert rows(app) == []

    @test()
    def test_a_new_row_deletes_the_orgs_rows_past_retention(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        clock = make_clock(self.env)
        raw_call(mcp, admin_token, "me_get")
        clock[0] = T0 + timedelta(days=91)
        raw_call(mcp, admin_token, "me_get")
        [row] = rows(app)
        assert row.hour.replace(tzinfo=UTC) == stats.hour_of(T0 + timedelta(days=91))

    # Criterion 3: mcp_tools_list

    @test()
    def test_tools_list_gives_definition_and_response_cost(self, suite_parameter):
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        make_clock(self.env)
        api = TestClient(mcp.app)
        api.headers["Authorization"] = f"Bearer {admin_token}"
        raw_call(mcp, admin_token, "me_get")
        listed = ok(api.get(url("/mcp/tools")))
        by_name = {item["name"]: item for item in listed["items"]}
        assert len(by_name) == TOOL_COUNT and MCP_OPS <= set(by_name)
        live = rpc(mcp, admin_token, "tools/list", query="?toolsets=all").json()["result"]["tools"]
        for entry in live:
            wire = json.dumps(entry, separators=(",", ":")).encode()
            assert by_name[entry["name"]]["def_tokens"] == math.ceil(len(wire) / 4), entry["name"]
        assert listed["total_def_tokens"] == sum(item["def_tokens"] for item in listed["items"])
        me = by_name["me_get"]
        assert (me["calls_7d"], me["calls_30d"], me["errors_30d"]) == (1, 1, 0)
        assert me["p50_resp_tokens"] == me["p95_resp_tokens"] > 0
        assert by_name["cases_list"]["calls_30d"] == 0 and by_name["cases_list"]["p50_resp_tokens"] is None
        assert by_name["mcp_usage"]["read_only"] is True and by_name["mcp_usage"]["toolset"] == "admin"

    @test()
    def test_tools_list_counts_7_and_30_days_apart(self, suite_parameter):
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        clock = make_clock(self.env)
        raw_call(mcp, admin_token, "me_get")
        clock[0] = T0 + timedelta(days=10)
        raw_call(mcp, admin_token, "me_get")
        api = TestClient(mcp.app)
        api.headers["Authorization"] = f"Bearer {admin_token}"
        me = {i["name"]: i for i in ok(api.get(url("/mcp/tools")))["items"]}["me_get"]
        assert (me["calls_7d"], me["calls_30d"]) == (1, 2)

    # Criterion 4: mcp_usage and mcp_server_get

    @test()
    def test_usage_buckets_by_hour_and_day_filtered_by_tool_and_actor(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        owner = self.env.owner
        clock = make_clock(self.env)
        admin = token(owner, "admin", "read")
        add_member(owner, "eddie@example.com", "admin")
        eddie = self.env.client()
        login(eddie, "eddie@example.com")
        other = token(eddie, "read")
        raw_call(mcp, admin, "me_get")
        raw_call(mcp, other, "me_get")
        clock[0] = T0 + timedelta(hours=2)
        raw_call(mcp, admin, "me_get")
        assert call(mcp, admin, "orgs_get", org="nope")["status"] >= 400
        owner_actor = next(r.actor_id for r in rows(app) if r.tool == "orgs_get")

        api = self.env.bearer(admin)
        hourly = ok(
            api.get(
                url("/mcp/usage"), params={"since": "2026-11-14T00:00:00Z", "until": "2026-11-15T00:00:00Z"}
            )
        )
        assert hourly["bucket"] == "hour"
        assert [(b["start"][:13], b["calls"], b["errors"]) for b in hourly["items"]] == [
            ("2026-11-14T10", 2, 0),
            ("2026-11-14T12", 2, 1),
        ]
        assert all(b["p50_resp_tokens"] <= b["p95_resp_tokens"] for b in hourly["items"])
        daily = ok(api.get(url("/mcp/usage"), params={"bucket": "day", "since": "2026-11-10T05:00:00Z"}))
        assert daily["since"].startswith("2026-11-10T00:00:00")
        assert [(b["start"][:10], b["calls"]) for b in daily["items"]] == [("2026-11-14", 4)]
        by_tool = ok(api.get(url("/mcp/usage"), params={"bucket": "day", "tool": "orgs_get"}))["items"]
        assert [(b["calls"], b["errors"]) for b in by_tool] == [(1, 1)]
        by_actor = ok(api.get(url("/mcp/usage"), params={"bucket": "day", "actor": owner_actor}))["items"]
        assert by_actor[0]["calls"] == 3
        mine = ok(
            api.get(url("/mcp/usage"), params={"bucket": "day", "actor": owner_actor, "tool": "me_get"})
        )
        assert mine["items"][0]["calls"] == 2

    @test()
    def test_usage_rejects_a_bad_bucket_or_range(self, suite_parameter):
        owner = self.env.owner
        make_clock(self.env)
        api = self.env.bearer(token(owner, "admin"))
        assert api.get(url("/mcp/usage"), params={"bucket": "week"}).status_code == 422
        backwards = {"since": "2026-11-14T10:00:00Z", "until": "2026-11-14T09:00:00Z"}
        assert api.get(url("/mcp/usage"), params=backwards).status_code == 422
        too_long = {"bucket": "day", "since": "2026-01-01T00:00:00Z"}
        assert api.get(url("/mcp/usage"), params=too_long).status_code == 422

    @test()
    def test_server_get_gives_the_version_and_tool_list_hash(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        api = TestClient(app)
        api.headers["Authorization"] = f"Bearer {admin_token}"
        server = ok(api.get(url("/mcp/server")))
        assert server["version"] == __version__ and server["tool_count"] == TOOL_COUNT
        assert server["tool_list_hash"] == tool_list_hash(build_tools(app))
        over_mcp = call_all(mcp, admin_token, "mcp_server_get", org="acme")["structuredContent"]
        assert over_mcp["status"] == 200 and over_mcp["data"] == server

    # The app's MCP page: custom ranges, reads and writes, clients and the updates feed

    @test()
    def test_tools_list_counts_calls_over_a_custom_range(self, suite_parameter):
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        clock = make_clock(self.env)
        raw_call(mcp, admin_token, "me_get")
        clock[0] = T0 + timedelta(days=10)
        raw_call(mcp, admin_token, "me_get")
        assert call(mcp, admin_token, "orgs_get", org="nope")["status"] >= 400
        api = self.env.bearer(admin_token)

        def tools(**params):
            listed = ok(api.get(url("/mcp/tools"), params=params))
            return listed, {i["name"]: i for i in listed["items"]}

        listed, by_name = tools()
        assert listed["since"].startswith("2026-10-25T11:00:00") and listed["until"].startswith("2026-11-24T11")
        assert (by_name["me_get"]["calls"], by_name["orgs_get"]["errors"]) == (2, 1)
        listed, by_name = tools(since="2026-11-14T11:30:00Z", until="2026-11-30T00:00:00Z")
        assert listed["since"].startswith("2026-11-14T11:00:00")
        assert (by_name["me_get"]["calls"], by_name["me_get"]["calls_30d"]) == (1, 2)
        assert by_name["me_get"]["p50_resp_tokens"] > 0
        _, by_name = tools(since="2026-11-01T00:00:00Z", until="2026-11-14T00:00:00Z")
        assert by_name["me_get"]["calls"] == 0 and by_name["me_get"]["p50_resp_tokens"] is None
        backwards = {"since": "2026-11-14T10:00:00Z", "until": "2026-11-14T09:00:00Z"}
        assert api.get(url("/mcp/tools"), params=backwards).status_code == 422
        too_long = {"since": "2026-01-01T00:00:00Z"}
        assert api.get(url("/mcp/tools"), params=too_long).status_code == 422

    @test()
    def test_usage_splits_reads_and_writes_and_a_removed_tool_counts_as_a_write(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        make_clock(self.env)
        raw_call(mcp, admin_token, "me_get")
        [seen] = rows(app)
        writer = next(t.name for t in app.state.mcp_tools if not t.annotations["read_only_hint"])
        for tool in (writer, "a_tool_no_longer_served"):
            stats.record(app.state.sessionmaker, seen.org_id, seen.actor_id, tool, 200, 10, 0)
        usage = ok(self.env.bearer(admin_token).get(url("/mcp/usage")))
        [bucket] = usage["items"]
        assert (bucket["calls"], bucket["reads"], bucket["writes"]) == (3, 1, 2)

    @test()
    def test_clients_lists_each_actor_with_its_name_and_kind_most_calls_first(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        owner = self.env.owner
        clock = make_clock(self.env)
        add_member(owner, "eddie@example.com", "admin")
        eddie = self.env.client()
        login(eddie, "eddie@example.com")
        admin = token(owner, "admin", "read")
        raw_call(mcp, token(eddie, "read"), "me_get")
        clock[0] = T0 + timedelta(hours=2)
        raw_call(mcp, admin, "me_get")
        assert call(mcp, admin, "orgs_get", org="nope")["status"] >= 400
        with app.state.sessionmaker() as db:
            names = {a.id: (a.name, a.kind) for a in db.scalars(select(Actor))}
        api = self.env.bearer(admin)
        clients = ok(api.get(url("/mcp/clients")))
        assert clients["since"].startswith("2026-11-13T13:00:00")
        first, second = clients["items"]
        assert (first["calls"], first["errors"], second["calls"], second["errors"]) == (2, 1, 1, 0)
        for item in (first, second):
            assert (item["name"], item["kind"]) == names[item["actor_id"]]
        assert first["last_hour"].startswith("2026-11-14T12") and second["last_hour"].startswith("2026-11-14T10")
        later = ok(api.get(url("/mcp/clients"), params={"since": "2026-11-14T11:00:00Z"}))["items"]
        assert [i["actor_id"] for i in later] == [first["actor_id"]]
        assert api.get(url("/mcp/clients"), params={"since": "2026-01-01T00:00:00Z"}).status_code == 422

    @test()
    def test_each_server_start_adds_one_update_and_a_changed_list_names_its_tools(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        sessionmaker = app.state.sessionmaker
        tools = app.state.mcp_tools
        events.record_start(sessionmaker, tools)
        changed = [
            *tools[2:],
            dataclasses.replace(tools[1], description=tools[1].description + " Changed."),
            dataclasses.replace(tools[0], name="zz_new_tool"),
        ]
        events.record_start(sessionmaker, changed)
        events.record_start(sessionmaker, changed)
        api = self.env.bearer(admin_token)
        page = ok(api.get(url("/mcp/updates"), params={"limit": 2}))
        rest = ok(api.get(url("/mcp/updates"), params={"limit": 2, "cursor": page["next_cursor"]}))
        assert rest["next_cursor"] is None
        newest, change, restart, first = page["items"] + rest["items"]
        assert [u["kind"] for u in (newest, change, restart, first)] == [
            "server_started",
            "tools_changed",
            "server_started",
            "server_started",
        ]
        assert first["tool_list_hash"] == restart["tool_list_hash"] == app.state.mcp_tool_hash
        assert (change["added"], change["removed"], change["changed"]) == (
            ["zz_new_tool"],
            [tools[0].name],
            [tools[1].name],
        )
        assert change["tool_list_hash"] == newest["tool_list_hash"] == tool_list_hash(changed)
        assert all(u["version"] == __version__ for u in (newest, change, restart, first))
        assert all((u["added"], u["removed"], u["changed"]) == ([], [], []) for u in (newest, restart, first))
        over_mcp = call_all(mcp, admin_token, "mcp_updates", org="acme", limit=2)["structuredContent"]
        assert over_mcp["status"] == 200 and over_mcp["data"] == page

    @test()
    def test_a_failing_update_record_still_starts_the_server(self, suite_parameter):
        def boom(*args):
            raise RuntimeError("db down")

        self.env.patch(events, "record_start", boom)
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        assert call(mcp, admin_token, "me_get")["status"] == 200
        with self.env.app.state.sessionmaker() as db:
            assert db.scalars(select(McpServerEvent)).all() == []

    # The tool detail: description and hints, recent calls with status and latency, errors by code

    @test()
    def test_tools_list_gives_description_and_hints(self, suite_parameter):
        app = self.env.app
        self.mcp()
        api = self.env.bearer(token(self.env.owner, "admin", "read"))
        by_name = {i["name"]: i for i in ok(api.get(url("/mcp/tools")))["items"]}
        for tool in app.state.mcp_tools:
            item = by_name[tool.name]
            assert item["description"] == tool.description, tool.name
            assert (item["read_only"], item["idempotent"], item["destructive"]) == (
                tool.annotations["read_only_hint"],
                tool.annotations["idempotent_hint"],
                tool.annotations["destructive_hint"],
            ), tool.name
        archive, create, listing = by_name["cases_archive"], by_name["cases_create"], by_name["cases_list"]
        assert (archive["read_only"], archive["destructive"]) == (False, True)
        assert (create["idempotent"], create["destructive"]) == (True, False)
        assert (listing["read_only"], listing["idempotent"], listing["destructive"]) == (True, True, False)
        assert listing["description"]

    @test()
    def test_calls_list_each_call_newest_first_with_status_and_latency(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        clock = make_clock(self.env)
        size = raw_call(mcp, admin_token, "me_get")
        clock[0] = T0 + timedelta(minutes=5)
        bad = call_all(mcp, admin_token, "mcp_usage", org="acme", bucket="hour", since="2026-01-01T00:00:00Z")
        assert bad["structuredContent"]["status"] == 422
        with app.state.sessionmaker() as db:
            names = {a.id: (a.name, a.kind) for a in db.scalars(select(Actor))}
        api = self.env.bearer(admin_token)
        page = ok(api.get(url("/mcp/calls")))
        assert page["next_cursor"] is None
        newest, first = page["items"]
        assert (newest["tool"], newest["status"], first["tool"], first["status"]) == (
            "mcp_usage",
            422,
            "me_get",
            200,
        )
        assert newest["at"].startswith("2026-11-14T10:20") and first["at"].startswith("2026-11-14T10:15")
        assert all(item["ms"] >= 0 for item in (newest, first))
        assert first["resp_tokens"] == math.ceil(size / 4)
        assert (first["name"], first["kind"]) == names[first["actor_id"]]
        [last] = ok(api.get(url("/mcp/calls"), params={"limit": 1}))["items"]
        assert last["id"] == newest["id"]
        by_tool = ok(api.get(url("/mcp/calls"), params={"tool": "me_get"}))["items"]
        assert [i["id"] for i in by_tool] == [first["id"]]
        later = ok(api.get(url("/mcp/calls"), params={"since": "2026-11-14T10:16:00Z"}))["items"]
        assert [i["id"] for i in later] == [newest["id"]]
        paged = ok(api.get(url("/mcp/calls"), params={"limit": 1, "cursor": page["items"][0]["id"]}))
        assert [i["id"] for i in paged["items"]] == [first["id"]]
        assert api.get(url("/mcp/calls"), params={"limit": 101}).status_code == 422

    @test()
    def test_call_rows_past_7_days_are_pruned(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        clock = make_clock(self.env)
        for days in (0, 2, 8):
            clock[0] = T0 + timedelta(days=days)
            raw_call(mcp, admin_token, "me_get")
        with app.state.sessionmaker() as db:
            kept = sorted(row.at.replace(tzinfo=UTC) for row in db.scalars(select(McpToolCall)))
        assert kept == [T0 + timedelta(days=2), T0 + timedelta(days=8)]
        assert sum(row.calls for row in rows(app)) == 3

    @test()
    def test_a_call_takes_its_latency_from_dispatch(self, suite_parameter):
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        real_dispatch = server.dispatch

        async def slow_dispatch(*args):
            await anyio.sleep(0.05)
            return await real_dispatch(*args)

        self.env.patch(server, "dispatch", slow_dispatch)
        raw_call(mcp, admin_token, "me_get")
        [item] = ok(self.env.bearer(admin_token).get(url("/mcp/calls")))["items"]
        assert item["ms"] >= 50

    @test()
    def test_a_failing_call_row_insert_still_returns_the_result(self, suite_parameter):
        app = self.env.app
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")

        def boom(**kwargs):
            raise RuntimeError("db down")

        self.env.patch(stats, "McpToolCall", boom)
        assert call(mcp, admin_token, "me_get")["status"] == 200
        assert rows(app) == []  # one transaction: the hour row isn't kept without its call row

    @test()
    def test_tools_list_breaks_errors_down_by_code(self, suite_parameter):
        mcp = self.mcp()
        admin_token = token(self.env.owner, "admin", "read")
        clock = make_clock(self.env)
        too_long = {"org": "acme", "since": "2026-01-01T00:00:00Z"}
        assert call_all(mcp, admin_token, "mcp_usage", **too_long)["structuredContent"]["status"] == 422
        clock[0] = T0 + timedelta(days=10)
        for _ in range(2):
            assert call_all(mcp, admin_token, "mcp_usage", **too_long)["structuredContent"]["status"] == 422
        assert call_all(mcp, admin_token, "mcp_usage", org="nope")["structuredContent"]["status"] == 404
        raw_call(mcp, admin_token, "mcp_usage", org="acme")
        api = self.env.bearer(admin_token)
        usage = {i["name"]: i for i in ok(api.get(url("/mcp/tools")))["items"]}["mcp_usage"]
        assert (usage["calls"], usage["errors"]) == (5, 4)
        assert usage["errors_by_code"] == {"404": 1, "422": 3}
        assert sum(usage["errors_by_code"].values()) == usage["errors"]
        recent = ok(api.get(url("/mcp/tools"), params={"since": "2026-11-20T00:00:00Z"}))["items"]
        usage = {i["name"]: i for i in recent}["mcp_usage"]
        assert (usage["errors"], usage["errors_by_code"]) == (3, {"404": 1, "422": 2})
        assert {i["name"]: i for i in recent}["me_get"]["errors_by_code"] == {}

    # Criterion 5: admin or audit:read

    @test(parameters=[(("admin",), True), (("audit:read",), True), (("read",), False)])
    def test_the_ops_need_admin_or_audit_read(self, suite_parameter, parameter):
        scopes, allowed = parameter
        mcp = self.mcp()
        owner = self.env.owner
        value = token(owner, *scopes)
        api = self.env.bearer(value)
        for path in ("/mcp/tools", "/mcp/usage", "/mcp/server", "/mcp/clients", "/mcp/updates", "/mcp/calls"):
            response = api.get(url(path))
            assert response.status_code == (200 if allowed else 403), (path, response.text)
            if not allowed:
                assert response.json()["detail"] == "Needs scope admin or audit:read"
        visible = tool_names(mcp, value, "?toolsets=all")
        assert (MCP_OPS <= visible) is allowed and (MCP_OPS & visible) == (MCP_OPS if allowed else set())
        for name in MCP_OPS:
            result = call_all(mcp, value, name, org="acme")["structuredContent"]
            assert result["status"] == (200 if allowed else 404), (name, result)

    @test()
    def test_an_admin_only_token_can_also_read_the_audit_log(self, suite_parameter):
        mcp = self.mcp()
        owner = self.env.owner
        value = token(owner, "admin")
        assert self.env.bearer(value).get(url("/audit")).status_code == 200
        assert call_all(mcp, value, "audit_list", org="acme")["structuredContent"]["status"] == 200


@Suite()
class McpStatsNoDb:
    @test()
    def test_histogram_percentiles_are_bucket_upper_bounds(self):
        assert stats.bucket_of(0) == stats.bucket_of(1) == 0
        assert stats.bucket_of(1024) == stats.bucket_of(2047) == 10
        assert stats.bucket_of(10**12) == stats.HIST_BUCKETS - 1
        hist = [0] * stats.HIST_BUCKETS
        hist[10] = 19  # 1-2 KiB
        hist[14] = 1  # 16-32 KiB
        assert stats.percentiles(hist) == (512, 512)
        hist[14] = 2
        assert stats.percentiles(hist) == (512, 8192)
        assert stats.percentiles([0] * stats.HIST_BUCKETS) == (None, None)
