"""The MCP page's numbers: per-tool token cost and usage, and the server's version (PLAN-100).

Token figures are bytes ÷ 4. Response p50/p95 come from each row's log2 histogram, so they are bucket upper
bounds, at most 2x the true size. Read-only and not audited, like `audit_list`; the UI polls them.
"""

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms import __version__
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_any_scope
from test_junkie_tcms.auth.scopes import ADMIN, AUDIT_READ
from test_junkie_tcms.db.base import aware
from test_junkie_tcms.db.models import McpToolStat
from test_junkie_tcms.mcp_server import stats
from test_junkie_tcms.mcp_server.generator import ToolSpec, build_tools, def_tokens, tool_list_hash

router = APIRouter(tags=["mcp"])

SERVER_NAME = "test-junkie-tcms"
MAX_SPAN = timedelta(days=90)
BUCKETS = {"hour": timedelta(hours=1), "day": timedelta(days=1)}
DEFAULT_SPAN = {"hour": timedelta(hours=24), "day": timedelta(days=30)}


class McpToolOut(BaseModel):
    name: str
    toolset: str
    scope: str | None
    read_only: bool
    def_tokens: int
    calls_7d: int
    errors_7d: int
    calls_30d: int
    errors_30d: int
    p50_resp_tokens: int | None
    p95_resp_tokens: int | None


class McpToolsOut(BaseModel):
    items: list[McpToolOut]
    total_def_tokens: int


class McpUsageBucket(BaseModel):
    start: datetime
    calls: int
    errors: int
    resp_bytes: int
    p50_resp_tokens: int | None
    p95_resp_tokens: int | None


class McpUsageOut(BaseModel):
    bucket: Literal["hour", "day"]
    since: datetime
    until: datetime
    items: list[McpUsageBucket]


class McpServerOut(BaseModel):
    name: str
    version: str
    tool_count: int
    tool_list_hash: str


def _tools(request: Request) -> list[ToolSpec]:
    """The tools the running MCP server serves; built from the routes when it isn't running."""
    return getattr(request.app.state, "mcp_tools", None) or build_tools(request.app)


def _floor(value: datetime, bucket: str) -> datetime:
    value = stats.hour_of(aware(value))
    return value.replace(hour=0) if bucket == "day" else value


def _ceil(value: datetime, bucket: str) -> datetime:
    floor = _floor(value, bucket)
    return floor if floor == aware(value) else floor + BUCKETS[bucket]


def _rows(db: Session, org_id: str, since: datetime, until: datetime | None = None, tool=None, actor=None):
    query = select(McpToolStat).where(McpToolStat.org_id == org_id, McpToolStat.hour >= since)
    if until is not None:
        query = query.where(McpToolStat.hour < until)
    if tool:
        query = query.where(McpToolStat.tool == tool)
    if actor:
        query = query.where(McpToolStat.actor_id == actor)
    return db.scalars(query).all()


@router.get("/orgs/{org}/mcp/tools", response_model=McpToolsOut, **op("mcp_tools_list", AUDIT_READ, "admin"))
def mcp_tools_list(
    request: Request,
    ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ)),
    db: Session = Depends(get_db),
):
    """Every MCP tool with its definition cost in ≈ tokens (bytes ÷ 4), its calls and errors over the last 7
    and 30 days, and its p50/p95 response cost over 30 days (an upper bound, ≤2x; null with no calls)."""
    now = stats.now()
    week = now - timedelta(days=7)
    by_tool: dict[str, list[McpToolStat]] = {}
    for row in _rows(db, ctx.org.id, now - timedelta(days=30)):
        by_tool.setdefault(row.tool, []).append(row)
    items = []
    for tool in _tools(request):
        rows = by_tool.get(tool.name, [])
        recent = [row for row in rows if aware(row.hour) >= stats.hour_of(week)]
        p50, p95 = stats.percentiles(stats.merge(row.resp_bytes_hist for row in rows))
        items.append(
            McpToolOut(
                name=tool.name,
                toolset=tool.toolset,
                scope=tool.scope,
                read_only=tool.annotations["read_only_hint"],
                def_tokens=def_tokens(tool),
                calls_7d=sum(row.calls for row in recent),
                errors_7d=sum(row.errors for row in recent),
                calls_30d=sum(row.calls for row in rows),
                errors_30d=sum(row.errors for row in rows),
                p50_resp_tokens=p50,
                p95_resp_tokens=p95,
            )
        )
    return McpToolsOut(items=items, total_def_tokens=sum(item.def_tokens for item in items))


@router.get("/orgs/{org}/mcp/usage", response_model=McpUsageOut, **op("mcp_usage", AUDIT_READ, "admin"))
def mcp_usage(
    since: datetime | None = Query(None, description="From this time, inclusive; truncated to the bucket"),
    until: datetime | None = Query(None, description="Up to this time, exclusive; rounded up to the bucket"),
    bucket: Literal["hour", "day"] = Query("hour"),
    tool: str | None = Query(None, description="Exact tool name"),
    actor: str | None = Query(None, description="Actor id"),
    ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ)),
    db: Session = Depends(get_db),
):
    """MCP calls, errors and response bytes per hour or day (UTC), with p50/p95 response cost in ≈ tokens (an
    upper bound, ≤2x). Only buckets with calls are listed. Defaults: the last 24 hours by hour, or the last 30
    days by day; at most 90 days."""
    until = _ceil(until or stats.now(), bucket)
    since = _floor(since, bucket) if since else until - DEFAULT_SPAN[bucket]
    if since >= until:
        raise HTTPException(422, "since must be before until")
    if until - since > MAX_SPAN:
        raise HTTPException(422, "The range is at most 90 days")
    grouped: dict[datetime, list[McpToolStat]] = {}
    for row in _rows(db, ctx.org.id, since, until, tool, actor):
        grouped.setdefault(_floor(row.hour, bucket), []).append(row)
    items = []
    for start in sorted(grouped):
        rows = grouped[start]
        p50, p95 = stats.percentiles(stats.merge(row.resp_bytes_hist for row in rows))
        items.append(
            McpUsageBucket(
                start=start,
                calls=sum(row.calls for row in rows),
                errors=sum(row.errors for row in rows),
                resp_bytes=sum(row.resp_bytes_sum for row in rows),
                p50_resp_tokens=p50,
                p95_resp_tokens=p95,
            )
        )
    return McpUsageOut(bucket=bucket, since=since, until=until, items=items)


@router.get(
    "/orgs/{org}/mcp/server", response_model=McpServerOut, **op("mcp_server_get", AUDIT_READ, "admin")
)
def mcp_server_get(request: Request, ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ))):
    """The MCP server's name, version, tool count and a hash of its tool list, which changes with any tool."""
    tools = _tools(request)
    digest = (
        getattr(request.app.state, "mcp_tool_hash", None)
        if tools is getattr(request.app.state, "mcp_tools", None)
        else None
    )
    return McpServerOut(
        name=SERVER_NAME,
        version=__version__,
        tool_count=len(tools),
        tool_list_hash=digest or tool_list_hash(tools),
    )
