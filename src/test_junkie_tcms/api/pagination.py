"""Cursor pagination by ULID id: the cursor is the last id of the previous page."""

from typing import Any

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select
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


def paginate(db: Session, query: Select, id_column, params: PageParams) -> tuple[list[Any], str | None]:
    if params.cursor:
        query = query.where(id_column > params.cursor)
    rows = list(db.scalars(query.order_by(id_column).limit(params.limit + 1)))
    if len(rows) > params.limit:
        rows = rows[: params.limit]
        return rows, rows[-1].id
    return rows, None
