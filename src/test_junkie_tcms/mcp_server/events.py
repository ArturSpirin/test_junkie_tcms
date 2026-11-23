"""The MCP updates feed: one `mcp_server_event` row each time the server starts.

The row is `tools_changed` when the tool list differs from the newest row's (naming the tools added, removed
and changed), else `server_started`. The first start ever is `server_started`: there is nothing to compare.
Every row carries the version. Each worker process starts its own server, so several workers write one row
each; only the first of them can be `tools_changed`, since the others then see the same hash.
"""

import logging

from sqlalchemy import select
from ulid import ULID

from test_junkie_tcms import __version__
from test_junkie_tcms.db.models import McpServerEvent
from test_junkie_tcms.mcp_server import stats
from test_junkie_tcms.mcp_server.generator import ToolSpec, tool_hash, tool_list_hash

log = logging.getLogger(__name__)


def _next_id(last: McpServerEvent | None) -> str:
    """A new ULID that sorts after the newest row's, even within the same millisecond (ULID monotonicity)."""
    new = ULID()
    if last is not None and int(new) <= int(ULID.from_str(last.id)):
        new = ULID.from_int(int(ULID.from_str(last.id)) + 1)
    return str(new)


def record_start(sessionmaker, tools: list[ToolSpec]) -> McpServerEvent:
    """Write this start's row and return it."""
    hashes = {tool.name: tool_hash(tool) for tool in tools}
    digest = tool_list_hash(tools)
    db = sessionmaker()
    try:
        last = db.scalars(select(McpServerEvent).order_by(McpServerEvent.id.desc()).limit(1)).one_or_none()
        added: list[str] = []
        removed: list[str] = []
        changed: list[str] = []
        kind = "server_started"
        if last is not None and last.tool_list_hash != digest:
            kind = "tools_changed"
            before = last.tool_hashes
            added = sorted(set(hashes) - set(before))
            removed = sorted(set(before) - set(hashes))
            changed = sorted(name for name in set(hashes) & set(before) if hashes[name] != before[name])
        event = McpServerEvent(
            id=_next_id(last),
            at=stats.now(),
            kind=kind,
            version=__version__,
            tool_list_hash=digest,
            tool_hashes=hashes,
            added=added,
            removed=removed,
            changed=changed,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        db.expunge(event)
        return event
    finally:
        db.close()


def safe_record_start(sessionmaker, tools: list[ToolSpec]) -> None:
    """`record_start`, but the feed never stops the server from starting."""
    try:
        record_start(sessionmaker, tools)
    except Exception:
        log.exception("MCP updates: could not record the server start")
