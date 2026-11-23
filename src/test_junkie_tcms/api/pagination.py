"""Cursor pagination. By default by ULID id: the cursor is the last id of the previous page. With a
`SortKey`, a keyset on the sort values then the id: the cursor is an opaque token holding the last row's
values."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.orm import Session

MAX_LIMIT = 200


class PageParams(BaseModel):
    cursor: str | None = None
    limit: int = 50


def page_params(
    cursor: str | None = Query(None, description="next_cursor from the previous page"),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
) -> PageParams:
    return PageParams(cursor=cursor, limit=limit)


@dataclass(frozen=True)
class SortKey:
    """Order by `exprs`, then the id, all ascending or all descending. Each expression must be non-null."""

    exprs: tuple[Any, ...]
    desc: bool = False


def count(db: Session, query: Select) -> int:
    """Rows the query matches, before any cursor or limit: a list's `total`."""
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))


def paginate(
    db: Session,
    query: Select,
    id_column,
    params: PageParams,
    newest_first: bool = False,
    sort: SortKey | None = None,
) -> tuple[list[Any], str | None, int]:
    """One page of the query's rows, the next page's cursor (None on the last page), and the total."""
    total = count(db, query)
    if sort is not None:
        return *_sorted_page(db, query, id_column, params, sort), total
    if params.cursor:
        query = query.where(id_column < params.cursor if newest_first else id_column > params.cursor)
    order = id_column.desc() if newest_first else id_column
    rows = list(db.scalars(query.order_by(order).limit(params.limit + 1)))
    if len(rows) > params.limit:
        rows = rows[: params.limit]
        return rows, rows[-1].id, total
    return rows, None, total


def _sorted_page(
    db: Session, query: Select, id_column, params: PageParams, sort: SortKey
) -> tuple[list[Any], str | None]:
    keys = (*sort.exprs, id_column)
    if params.cursor:
        after = tuple_(*keys), tuple_(*_decode(params.cursor, len(keys)))
        query = query.where(after[0] < after[1] if sort.desc else after[0] > after[1])
    order = [k.desc() for k in keys] if sort.desc else list(keys)
    rows = list(db.execute(query.add_columns(*sort.exprs).order_by(*order).limit(params.limit + 1)))
    cursor = None
    if len(rows) > params.limit:
        rows = rows[: params.limit]
        last = rows[-1]
        cursor = _encode([*last[1:], last[0].id])
    return [r[0] for r in rows], cursor


def _encode(values: list[Any]) -> str:
    out = [{"t": v.isoformat()} if isinstance(v, datetime) else v for v in values]
    return base64.urlsafe_b64encode(json.dumps(out).encode()).decode().rstrip("=")


def _decode(cursor: str, n: int) -> list[Any]:
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(values, list) or len(values) != n:
            raise ValueError
        return [_time(v["t"]) if isinstance(v, dict) else v for v in values]
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise HTTPException(422, "cursor is not a next_cursor of this list and sort") from None


def _time(value: str) -> datetime:
    """A cursor's time as stored: UTC, naive on SQLite (which keeps no zone)."""
    t = datetime.fromisoformat(value)
    return t if t.tzinfo is None else t.astimezone(UTC)
