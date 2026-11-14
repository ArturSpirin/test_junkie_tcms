"""`Idempotency-Key` on org-scoped POSTs: a retried request returns the first result instead of running twice.

The `idempotency` dependency adds a `pending` record to the request's own session, so the handler's single
commit writes its data and the record together: a crash can't leave the data written and the key free. The
`IdempotencyRecorder` middleware then stores the response on that record, and a later request with the same
key replays it.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta

import anyio
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select, update

from test_junkie_tcms.auth.deps import OrgContext, get_db, get_org_context
from test_junkie_tcms.db.base import aware, new_id, utcnow
from test_junkie_tcms.db.models import IdempotencyRecord

TTL = timedelta(hours=24)
STATE_KEY = "idempotency_record_id"
REPLAYED = "Idempotent-Replayed"
# Response headers a replay repeats.
KEPT_HEADERS = ("content-type", "etag", "location")


@dataclass
class Idem:
    key: str | None = None
    record_id: str | None = None


class Replay(Exception):
    def __init__(self, record: IdempotencyRecord):
        self.record = record


async def _request_hash(request: Request) -> str:
    body = await request.body()  # Starlette caches it, so the handler still gets it
    query = sorted(request.query_params.multi_items())
    parts = [request.method, request.url.path, json.dumps(query), body.decode("utf-8", "replace")]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def idempotency(
    request: Request,
    key: str | None = Header(
        None,
        alias="Idempotency-Key",
        max_length=255,
        description="Optional. A retry with the same key returns the first result for 24 h",
    ),
    request_hash: str = Depends(_request_hash),
    ctx: OrgContext = Depends(get_org_context),
    db=Depends(get_db),
) -> Idem:
    """Declare after the route's scope dependency; a request without the header runs as usual."""
    if key is None:
        return Idem()
    if not key:
        raise HTTPException(422, "Idempotency-Key must not be empty")
    now = utcnow()
    rec = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.org_id == ctx.org.id,
            IdempotencyRecord.actor_id == ctx.actor.id,
            IdempotencyRecord.key == key,
        )
    )
    fresh = {
        "method": request.method,
        "path": request.url.path[:500],
        "request_hash": request_hash,
        "state": "pending",
        "status_code": None,
        "response_body": None,
        "response_headers": None,
        "expires_at": now + TTL,
    }
    if rec is None:
        rec = IdempotencyRecord(id=new_id(), org_id=ctx.org.id, actor_id=ctx.actor.id, key=key, **fresh)
        db.add(rec)
    elif aware(rec.expires_at) <= now:
        # Reuse the expired row in place: a delete and an insert in one flush would hit the UNIQUE key.
        for field, value in fresh.items():
            setattr(rec, field, value)
    elif rec.request_hash != request_hash:
        raise HTTPException(422, "Idempotency-Key was already used with a different request")
    elif rec.state == "pending":
        raise HTTPException(
            409,
            "A request with this Idempotency-Key is still running, or its result was not recorded:"
            " read the resource before retrying",
        )
    else:
        raise Replay(rec)
    request.state.idempotency_record_id = rec.id
    return Idem(key=key, record_id=rec.id)


async def _replay(request: Request, exc: Replay) -> Response:
    rec = exc.record
    headers = dict(rec.response_headers or {})
    headers[REPLAYED] = "true"
    content = b"" if rec.response_body is None else json.dumps(rec.response_body).encode()
    return Response(content, status_code=rec.status_code, headers=headers)


def _store(sessionmaker, record_id: str, status: int, headers: dict[str, str], body: bytes) -> None:
    try:
        stored_body = json.loads(body) if body else None
    except ValueError:
        stored_body = body.decode("utf-8", "replace")
    with sessionmaker() as db:
        # Matches 0 rows when the handler never committed the record: nothing recorded, a retry runs fresh.
        db.execute(
            update(IdempotencyRecord)
            .where(IdempotencyRecord.id == record_id, IdempotencyRecord.state == "pending")
            .values(state="done", status_code=status, response_body=stored_body, response_headers=headers)
        )
        db.commit()


class IdempotencyRecorder:
    """Pure ASGI: buffers only the responses the dependency marked, and stores them before sending."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        start: dict | None = None
        chunks: list[bytes] = []

        async def recording_send(message):
            nonlocal start
            record_id = scope.get("state", {}).get(STATE_KEY)
            if record_id is None:
                await send(message)
                return
            if message["type"] == "http.response.start":
                start = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return
            body = b"".join(chunks)
            status = start["status"]
            # Handlers commit once, at the end, so an error response never committed the pending record:
            # nothing to store (and on SQLite the request session still holds the write lock).
            if status < 400:
                headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1")
                    for k, v in start.get("headers", [])
                    if k.decode("latin-1").lower() in KEPT_HEADERS
                }
                sessionmaker = scope["app"].state.sessionmaker
                await anyio.to_thread.run_sync(_store, sessionmaker, record_id, status, headers, body)
            await send(start)
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, recording_send)


def install(app: FastAPI) -> None:
    app.add_exception_handler(Replay, _replay)
    app.add_middleware(IdempotencyRecorder)
