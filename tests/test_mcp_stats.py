"""T5b: per-tool MCP stats recorded on each `/mcp` call, and the three MCP page operations (PLAN-100)."""

import json
import math
from datetime import UTC, datetime, timedelta

import pytest
from catalog_seed import ok, url
from conftest import add_member, bearer, login
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_mcp_server import call, rpc, token, tool_names

from test_junkie_tcms import __version__
from test_junkie_tcms.db.models import McpToolStat
from test_junkie_tcms.mcp_server import stats
from test_junkie_tcms.mcp_server.generator import build_tools, tool_list_hash

T0 = datetime(2026, 11, 14, 10, 15, tzinfo=UTC)
MCP_OPS = {"mcp_tools_list", "mcp_usage", "mcp_server_get"}


@pytest.fixture
def mcp(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin_token(owner):
    return token(owner, "admin", "read")


@pytest.fixture
def clock(monkeypatch):
    """`stats.now()` at a set time; move it with `clock[0] = ...`."""
    at = [T0]
    monkeypatch.setattr(stats, "now", lambda: at[0])
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


# Criterion 2: recording


def test_each_call_adds_to_its_hours_row(app, mcp, admin_token, clock):
    sizes = [raw_call(mcp, admin_token, "me_get") for _ in range(2)]
    assert call(mcp, admin_token, "orgs_get", org="nope")["status"] >= 400
    clock[0] = T0 + timedelta(hours=1)
    raw_call(mcp, admin_token, "me_get")
    me, me_next, org = rows(app)
    assert (me.tool, me.calls, me.errors, me.resp_bytes_sum) == ("me_get", 2, 0, sum(sizes))
    assert me.hour.replace(tzinfo=UTC) == datetime(2026, 11, 14, 10, tzinfo=UTC)
    assert sum(me.resp_bytes_hist) == 2 and me.resp_bytes_hist[stats.bucket_of(sizes[0])] >= 1
    assert me_next.calls == 1 and me_next.hour.replace(tzinfo=UTC) == datetime(2026, 11, 14, 11, tzinfo=UTC)
    assert (org.tool, org.calls, org.errors) == ("orgs_get", 1, 1)
    assert me.actor_id == org.actor_id


def test_an_unknown_or_hidden_tool_is_not_recorded(app, mcp, owner):
    value = token(owner, "read")
    for name in ("nope", "mcp_usage"):
        assert call_all(mcp, value, name, org="acme")["structuredContent"]["status"] == 404
    assert rows(app) == []


def test_each_actor_gets_its_own_row(app, mcp, owner, client_factory):
    add_member(owner, "eddie@example.com", "admin")
    eddie = client_factory()
    login(eddie, "eddie@example.com")
    for value in (token(owner, "read"), token(eddie, "read")):
        raw_call(mcp, value, "me_get")
    first, second = rows(app)
    assert first.calls == second.calls == 1 and first.actor_id != second.actor_id


def test_a_concurrent_insert_of_the_same_row_is_retried(app, mcp, admin_token, clock, monkeypatch):
    real_find = stats._find
    raced = []

    def find_after_a_racer(db, org_id, tool, actor_id, hour):
        if not raced:  # another call inserts this hour's row between our select and insert
            raced.append(True)
            stats.record(app.state.sessionmaker, org_id, actor_id, tool, False, 10)
            return None
        return real_find(db, org_id, tool, actor_id, hour)

    monkeypatch.setattr(stats, "_find", find_after_a_racer)
    raw_call(mcp, admin_token, "me_get")
    [row] = rows(app)
    assert row.calls == 2


def test_a_failing_record_still_returns_the_result(app, mcp, admin_token, monkeypatch):
    def boom(*args):
        raise RuntimeError("db down")

    monkeypatch.setattr(stats, "record", boom)
    assert call(mcp, admin_token, "me_get")["status"] == 200
    assert rows(app) == []


def test_a_new_row_deletes_the_orgs_rows_past_retention(app, mcp, admin_token, clock):
    raw_call(mcp, admin_token, "me_get")
    clock[0] = T0 + timedelta(days=91)
    raw_call(mcp, admin_token, "me_get")
    [row] = rows(app)
    assert row.hour.replace(tzinfo=UTC) == stats.hour_of(T0 + timedelta(days=91))


def test_histogram_percentiles_are_bucket_upper_bounds():
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


# Criterion 3: mcp_tools_list


def test_tools_list_gives_definition_and_response_cost(mcp, admin_token, clock):
    api = TestClient(mcp.app)
    api.headers["Authorization"] = f"Bearer {admin_token}"
    raw_call(mcp, admin_token, "me_get")
    listed = ok(api.get(url("/mcp/tools")))
    by_name = {item["name"]: item for item in listed["items"]}
    assert len(by_name) == 90 and MCP_OPS <= set(by_name)
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


def test_tools_list_counts_7_and_30_days_apart(mcp, admin_token, clock):
    raw_call(mcp, admin_token, "me_get")
    clock[0] = T0 + timedelta(days=10)
    raw_call(mcp, admin_token, "me_get")
    api = TestClient(mcp.app)
    api.headers["Authorization"] = f"Bearer {admin_token}"
    me = {i["name"]: i for i in ok(api.get(url("/mcp/tools")))["items"]}["me_get"]
    assert (me["calls_7d"], me["calls_30d"]) == (1, 2)


# Criterion 4: mcp_usage and mcp_server_get


def test_usage_buckets_by_hour_and_day_filtered_by_tool_and_actor(app, mcp, owner, client_factory, clock):
    admin = token(owner, "admin", "read")
    add_member(owner, "eddie@example.com", "admin")
    eddie = client_factory()
    login(eddie, "eddie@example.com")
    other = token(eddie, "read")
    raw_call(mcp, admin, "me_get")
    raw_call(mcp, other, "me_get")
    clock[0] = T0 + timedelta(hours=2)
    raw_call(mcp, admin, "me_get")
    assert call(mcp, admin, "orgs_get", org="nope")["status"] >= 400
    owner_actor = next(r.actor_id for r in rows(app) if r.tool == "orgs_get")

    api = bearer(client_factory, admin)
    hourly = ok(
        api.get(url("/mcp/usage"), params={"since": "2026-11-14T00:00:00Z", "until": "2026-11-15T00:00:00Z"})
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
    mine = ok(api.get(url("/mcp/usage"), params={"bucket": "day", "actor": owner_actor, "tool": "me_get"}))
    assert mine["items"][0]["calls"] == 2


def test_usage_rejects_a_bad_bucket_or_range(owner, client_factory, clock):
    api = bearer(client_factory, token(owner, "admin"))
    assert api.get(url("/mcp/usage"), params={"bucket": "week"}).status_code == 422
    backwards = {"since": "2026-11-14T10:00:00Z", "until": "2026-11-14T09:00:00Z"}
    assert api.get(url("/mcp/usage"), params=backwards).status_code == 422
    too_long = {"bucket": "day", "since": "2026-01-01T00:00:00Z"}
    assert api.get(url("/mcp/usage"), params=too_long).status_code == 422


def test_server_get_gives_the_version_and_tool_list_hash(app, mcp, admin_token):
    api = TestClient(app)
    api.headers["Authorization"] = f"Bearer {admin_token}"
    server = ok(api.get(url("/mcp/server")))
    assert server["version"] == __version__ and server["tool_count"] == 90
    assert server["tool_list_hash"] == tool_list_hash(build_tools(app))
    over_mcp = call_all(mcp, admin_token, "mcp_server_get", org="acme")["structuredContent"]
    assert over_mcp["status"] == 200 and over_mcp["data"] == server


# Criterion 5: admin or audit:read


@pytest.mark.parametrize(
    ("scopes", "allowed"), [(("admin",), True), (("audit:read",), True), (("read",), False)]
)
def test_the_ops_need_admin_or_audit_read(mcp, owner, client_factory, scopes, allowed):
    value = token(owner, *scopes)
    api = bearer(client_factory, value)
    for path in ("/mcp/tools", "/mcp/usage", "/mcp/server"):
        response = api.get(url(path))
        assert response.status_code == (200 if allowed else 403), (path, response.text)
        if not allowed:
            assert response.json()["detail"] == "Needs scope admin or audit:read"
    visible = tool_names(mcp, value, "?toolsets=all")
    assert (MCP_OPS <= visible) is allowed and (MCP_OPS & visible) == (MCP_OPS if allowed else set())
    for name in MCP_OPS:
        result = call_all(mcp, value, name, org="acme")["structuredContent"]
        assert result["status"] == (200 if allowed else 404), (name, result)


def test_an_admin_only_token_can_also_read_the_audit_log(mcp, owner, client_factory):
    value = token(owner, "admin")
    assert bearer(client_factory, value).get(url("/audit")).status_code == 200
    assert call_all(mcp, value, "audit_list", org="acme")["structuredContent"]["status"] == 200
