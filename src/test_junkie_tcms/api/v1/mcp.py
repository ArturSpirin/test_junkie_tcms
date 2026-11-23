"""The MCP page's numbers: per-tool token cost and usage, who calls, the server's version and its updates.

Token figures are bytes ÷ 4. Response p50/p95 come from each row's log2 histogram, so they are bucket upper
bounds, at most 2x the true size. Read-only and not audited, like `audit_list`; the UI polls them.
"""

import math
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms import __version__
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.schemas import Page, UtcDateTime
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_any_scope
from test_junkie_tcms.auth.scopes import ADMIN, AUDIT_READ
from test_junkie_tcms.db.base import aware
from test_junkie_tcms.db.models import Actor, McpServerEvent, McpToolCall, McpToolStat
from test_junkie_tcms.mcp_server import stats
from test_junkie_tcms.mcp_server.generator import ToolSpec, build_tools, def_tokens, tool_list_hash

router = APIRouter(tags=["mcp"])

SERVER_NAME = "test-junkie-tcms"
MAX_SPAN = timedelta(days=90)
MAX_CALLS = 100
BUCKETS = {"hour": timedelta(hours=1), "day": timedelta(days=1)}
DEFAULT_SPAN = {"hour": timedelta(hours=24), "day": timedelta(days=30)}


class McpToolOut(BaseModel):
    name: str
    toolset: str
    scope: str | None
    description: str
    read_only: bool
    idempotent: bool
    destructive: bool
    def_tokens: int
    calls_7d: int
    errors_7d: int
    calls_30d: int
    errors_30d: int
    calls: int
    errors: int
    errors_by_code: dict[str, int]
    p50_resp_tokens: int | None
    p95_resp_tokens: int | None


class McpToolsOut(BaseModel):
    since: datetime
    until: datetime
    items: list[McpToolOut]
    total_def_tokens: int


class McpUsageBucket(BaseModel):
    start: datetime
    calls: int
    reads: int
    writes: int
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


class McpClientOut(BaseModel):
    actor_id: str
    name: str
    kind: Literal["user", "agent"]
    calls: int
    errors: int
    last_hour: datetime


class McpClientsOut(BaseModel):
    since: datetime
    until: datetime
    items: list[McpClientOut]


class McpUpdateOut(BaseModel):
    id: str
    at: datetime
    kind: Literal["server_started", "tools_changed"]
    version: str
    tool_list_hash: str
    added: list[str]
    removed: list[str]
    changed: list[str]


class McpCallOut(BaseModel):
    id: str
    at: datetime
    tool: str
    actor_id: str
    name: str
    kind: Literal["user", "agent"]
    status: int
    ms: int
    resp_tokens: int


def _tools(request: Request) -> list[ToolSpec]:
    """The tools the running MCP server serves; built from the routes when it isn't running."""
    return getattr(request.app.state, "mcp_tools", None) or build_tools(request.app)


def _floor(value: datetime, bucket: str) -> datetime:
    value = stats.hour_of(aware(value))
    return value.replace(hour=0) if bucket == "day" else value


def _ceil(value: datetime, bucket: str) -> datetime:
    floor = _floor(value, bucket)
    return floor if floor == aware(value) else floor + BUCKETS[bucket]


def _range(
    since: datetime | None, until: datetime | None, bucket: str, default_span: timedelta | None = None
) -> tuple[datetime, datetime]:
    """The [since, until) a stats call covers: rounded out to whole buckets, `default_span` (else the bucket's)
    back from `until` when `since` is left out, at most 90 days. Every stats call uses it, so they can't drift."""
    until = _ceil(until or stats.now(), bucket)
    since = _floor(since, bucket) if since else until - (default_span or DEFAULT_SPAN[bucket])
    if since >= until:
        raise HTTPException(422, "since must be before until")
    if until - since > MAX_SPAN:
        raise HTTPException(422, "The range is at most 90 days")
    return since, until


SINCE = "From this time, inclusive; truncated to the hour (to the day for bucket=day)"
UNTIL = "Up to this time, exclusive; rounded up to the hour (to the day for bucket=day)"


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
    since: UtcDateTime | None = Query(None, description=SINCE),
    until: UtcDateTime | None = Query(None, description=UNTIL),
    ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ)),
    db: Session = Depends(get_db),
):
    """Every MCP tool with its description, its read-only, idempotent and destructive hints, its definition
    cost in ≈ tokens (bytes ÷ 4), its calls and errors over the last 7 and 30 days, and its `calls`, `errors`
    (`errors_by_code` splits them by HTTP status) and p50/p95 response cost (an upper bound, ≤2x; null with no
    calls) over `since`..`until`: by default the last 30 days, at most 90."""
    since, until = _range(since, until, "hour", timedelta(days=30))
    now = stats.now()
    week = now - timedelta(days=7)
    by_tool: dict[str, list[McpToolStat]] = {}
    for row in _rows(db, ctx.org.id, now - timedelta(days=30)):
        by_tool.setdefault(row.tool, []).append(row)
    in_range: dict[str, list[McpToolStat]] = {}
    for row in _rows(db, ctx.org.id, since, until):
        in_range.setdefault(row.tool, []).append(row)
    items = []
    for tool in _tools(request):
        rows = by_tool.get(tool.name, [])
        recent = [row for row in rows if aware(row.hour) >= stats.hour_of(week)]
        ranged = in_range.get(tool.name, [])
        p50, p95 = stats.percentiles(stats.merge(row.resp_bytes_hist for row in ranged))
        codes: dict[str, int] = {}
        for row in ranged:
            for code, count in (row.error_codes or {}).items():
                codes[code] = codes.get(code, 0) + count
        items.append(
            McpToolOut(
                name=tool.name,
                toolset=tool.toolset,
                scope=tool.scope,
                description=tool.description,
                read_only=tool.annotations["read_only_hint"],
                idempotent=tool.annotations["idempotent_hint"],
                destructive=tool.annotations["destructive_hint"],
                def_tokens=def_tokens(tool),
                calls_7d=sum(row.calls for row in recent),
                errors_7d=sum(row.errors for row in recent),
                calls_30d=sum(row.calls for row in rows),
                errors_30d=sum(row.errors for row in rows),
                calls=sum(row.calls for row in ranged),
                errors=sum(row.errors for row in ranged),
                errors_by_code=dict(sorted(codes.items())),
                p50_resp_tokens=p50,
                p95_resp_tokens=p95,
            )
        )
    return McpToolsOut(
        since=since, until=until, items=items, total_def_tokens=sum(item.def_tokens for item in items)
    )


@router.get("/orgs/{org}/mcp/usage", response_model=McpUsageOut, **op("mcp_usage", AUDIT_READ, "admin"))
def mcp_usage(
    request: Request,
    since: UtcDateTime | None = Query(None, description=SINCE),
    until: UtcDateTime | None = Query(None, description=UNTIL),
    bucket: Literal["hour", "day"] = Query("hour"),
    tool: str | None = Query(None, description="Exact tool name"),
    actor: str | None = Query(None, description="Actor id"),
    ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ)),
    db: Session = Depends(get_db),
):
    """MCP calls (split into `reads` and `writes`), errors and response bytes per hour or day (UTC), with
    p50/p95 response cost in ≈ tokens (an upper bound, ≤2x). Only buckets with calls are listed. Defaults: the
    last 24 hours by hour, or the last 30 days by day; at most 90 days. A read is a call to a tool the running
    server marks read-only; every other call, including one to a tool it no longer serves, is a write."""
    since, until = _range(since, until, bucket)
    read_only = {t.name for t in _tools(request) if t.annotations["read_only_hint"]}
    grouped: dict[datetime, list[McpToolStat]] = {}
    for row in _rows(db, ctx.org.id, since, until, tool, actor):
        grouped.setdefault(_floor(row.hour, bucket), []).append(row)
    items = []
    for start in sorted(grouped):
        rows = grouped[start]
        p50, p95 = stats.percentiles(stats.merge(row.resp_bytes_hist for row in rows))
        reads = sum(row.calls for row in rows if row.tool in read_only)
        calls = sum(row.calls for row in rows)
        items.append(
            McpUsageBucket(
                start=start,
                calls=calls,
                reads=reads,
                writes=calls - reads,
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


@router.get("/orgs/{org}/mcp/clients", response_model=McpClientsOut, **op("mcp_clients", AUDIT_READ, "admin"))
def mcp_clients(
    since: UtcDateTime | None = Query(None, description=SINCE),
    until: UtcDateTime | None = Query(None, description=UNTIL),
    ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ)),
    db: Session = Depends(get_db),
):
    """Who called MCP tools over `since`..`until` (by default the last 24 hours, at most 90 days): per actor
    (a member, `user`, or an AI agent, `agent`) its calls, errors and the latest UTC hour with a call, most
    calls first. A token acts as its actor, so calls made with it are counted there."""
    since, until = _range(since, until, "hour")
    by_actor: dict[str, list[McpToolStat]] = {}
    for row in _rows(db, ctx.org.id, since, until):
        by_actor.setdefault(row.actor_id, []).append(row)
    actors = {
        actor.id: actor
        for actor in db.scalars(select(Actor).where(Actor.org_id == ctx.org.id, Actor.id.in_(by_actor)))
    }
    items = [
        McpClientOut(
            actor_id=actor_id,
            name=actors[actor_id].name,
            kind=actors[actor_id].kind,
            calls=sum(row.calls for row in rows),
            errors=sum(row.errors for row in rows),
            last_hour=max(aware(row.hour) for row in rows),
        )
        for actor_id, rows in by_actor.items()
    ]
    items.sort(key=lambda item: (-item.calls, item.name, item.actor_id))
    return McpClientsOut(since=since, until=until, items=items)


@router.get("/orgs/{org}/mcp/calls", response_model=Page[McpCallOut], **op("mcp_calls", AUDIT_READ, "admin"))
def mcp_calls(
    since: UtcDateTime | None = Query(None, description="From this time, inclusive"),
    until: UtcDateTime | None = Query(None, description="Up to this time, exclusive"),
    tool: str | None = Query(None, description="Exact tool name"),
    actor: str | None = Query(None, description="Actor id"),
    cursor: str | None = Query(None, description="next_cursor from the previous page"),
    limit: int = Query(20, ge=1, le=MAX_CALLS),
    ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ)),
    db: Session = Depends(get_db),
):
    """The org's MCP calls over the last 7 days, newest first: each call's tool, caller (a member, `user`, or
    an AI agent, `agent`), HTTP status, latency in ms and response cost in ≈ tokens (bytes ÷ 4). `tool=` gives
    one tool's recent calls; `limit=1` the latest call. Calls are kept 7 days; arguments are not stored."""
    query = select(McpToolCall).where(McpToolCall.org_id == ctx.org.id)
    if since:
        query = query.where(McpToolCall.at >= since)
    if until:
        query = query.where(McpToolCall.at < until)
    if tool:
        query = query.where(McpToolCall.tool == tool)
    if actor:
        query = query.where(McpToolCall.actor_id == actor)
    rows, next_cursor, total = paginate(
        db, query, McpToolCall.id, PageParams(cursor=cursor, limit=limit), newest_first=True
    )
    actors = {
        a.id: a
        for a in db.scalars(
            select(Actor).where(Actor.org_id == ctx.org.id, Actor.id.in_({row.actor_id for row in rows}))
        )
    }
    return Page[McpCallOut](
        items=[
            McpCallOut(
                id=row.id,
                at=aware(row.at),
                tool=row.tool,
                actor_id=row.actor_id,
                name=actors[row.actor_id].name,
                kind=actors[row.actor_id].kind,
                status=row.status,
                ms=row.ms,
                resp_tokens=math.ceil(row.resp_bytes / 4),
            )
            for row in rows
        ],
        next_cursor=next_cursor,
        total=total,
    )


@router.get(
    "/orgs/{org}/mcp/updates", response_model=Page[McpUpdateOut], **op("mcp_updates", AUDIT_READ, "admin")
)
def mcp_updates(
    page: PageParams = Depends(page_params),
    ctx: OrgContext = Depends(require_any_scope(ADMIN, AUDIT_READ)),
    db: Session = Depends(get_db),
):
    """The MCP server's starts and tool-list changes, newest first. One row per start: `tools_changed` when
    its tool list differs from the previous row's (naming the tools added, removed and changed), else
    `server_started`. Server-wide: every org sees the same rows, which hold only tool names and versions."""
    query = select(McpServerEvent)
    rows, next_cursor, total = paginate(db, query, McpServerEvent.id, page, newest_first=True)
    return Page[McpUpdateOut](
        items=[
            McpUpdateOut(
                id=row.id,
                at=aware(row.at),
                kind=row.kind,
                version=row.version,
                tool_list_hash=row.tool_list_hash,
                added=row.added,
                removed=row.removed,
                changed=row.changed,
            )
            for row in rows
        ],
        next_cursor=next_cursor,
        total=total,
    )
