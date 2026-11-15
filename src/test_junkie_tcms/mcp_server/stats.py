"""Per-tool MCP usage: one `mcp_tool_stat` row per org, tool, actor and UTC hour (PLAN-27 §3, PLAN-100).

`call_tool` records each call after its result is built, in a worker thread with its own session, outside
the API call's transaction. Response sizes go into a fixed log2 histogram, so p50/p95 are bucket upper
bounds: at most 2x the true size, which is what the MCP page shows as "≈ tokens".
"""

import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import McpToolStat

log = logging.getLogger(__name__)

HIST_BUCKETS = 24
RETENTION = timedelta(days=90)


def now() -> datetime:
    return utcnow()  # patched in tests


def hour_of(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def bucket_of(size: int) -> int:
    """Bucket i holds sizes in [2^i, 2^(i+1)); bucket 0 also holds 0 and 1 B, the last everything above."""
    if size < 2:
        return 0
    return min(size.bit_length() - 1, HIST_BUCKETS - 1)


def merge(hists) -> list[int]:
    total = [0] * HIST_BUCKETS
    for hist in hists:
        for i, count in enumerate(hist[:HIST_BUCKETS]):
            total[i] += count
    return total


def percentiles(hist: list[int]) -> tuple[int | None, int | None]:
    """(p50, p95) response tokens by nearest rank: the bucket's upper bound 2^(i+1) bytes ÷ 4, rounded up."""
    calls = sum(hist)
    if not calls:
        return None, None
    out = []
    for p in (50, 95):
        rank = math.ceil(p / 100 * calls)
        seen = 0
        for i, count in enumerate(hist):
            seen += count
            if seen >= rank:
                out.append(math.ceil(2 ** (i + 1) / 4))
                break
    return out[0], out[1]


def _find(db: Session, org_id: str, tool: str, actor_id: str, hour: datetime) -> McpToolStat | None:
    return db.scalars(
        select(McpToolStat)
        .where(
            McpToolStat.org_id == org_id,
            McpToolStat.tool == tool,
            McpToolStat.actor_id == actor_id,
            McpToolStat.hour == hour,
        )
        .with_for_update()
    ).one_or_none()


def record(sessionmaker, org_id: str, actor_id: str, tool: str, error: bool, size: int) -> None:
    """Add one call to its hour's row. A new row also deletes the org's rows past retention."""
    hour = hour_of(now())
    for attempt in range(2):
        db = sessionmaker()
        try:
            row = _find(db, org_id, tool, actor_id, hour)
            if row is None:
                db.execute(
                    delete(McpToolStat).where(
                        McpToolStat.org_id == org_id, McpToolStat.hour < hour - RETENTION
                    )
                )
                row = McpToolStat(
                    org_id=org_id,
                    tool=tool,
                    actor_id=actor_id,
                    hour=hour,
                    calls=0,
                    errors=0,
                    resp_bytes_sum=0,
                    resp_bytes_hist=[0] * HIST_BUCKETS,
                )
                db.add(row)
            hist = list(row.resp_bytes_hist)
            hist[bucket_of(size)] += 1
            row.calls += 1
            row.errors += int(error)
            row.resp_bytes_sum += size
            row.resp_bytes_hist = hist
            db.commit()
            return
        except IntegrityError:
            # Another call inserted this hour's row first: retry once, which finds and updates it.
            db.rollback()
            if attempt:
                raise
        finally:
            db.close()


def safe_record(sessionmaker, org_id: str, actor_id: str, tool: str, error: bool, size: int) -> None:
    """`record`, but stats never fail a tool call."""
    try:
        record(sessionmaker, org_id, actor_id, tool, error, size)
    except Exception:
        log.exception("MCP stats: could not record a call to %s", tool)
