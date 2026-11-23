"""Consumer pairing by device code (RFC 8628). Only hashes of the device code and token
are stored; the token is shown once."""

import hashlib
import secrets
import time
from collections import deque
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.v1.consumers import (
    check_name_free,
    check_products,
    consumer_out,
    consumer_project_counts,
)
from test_junkie_tcms.api.v1.schemas import (
    ConsumerOut,
    PairingApprove,
    PairingCreated,
    PairingDeny,
    PairingIn,
    PairingPreview,
    PairingToken,
    PairingTokenIn,
)
from test_junkie_tcms.auth.deps import OrgContext, Principal, get_db, require_scope
from test_junkie_tcms.auth.scopes import ADMIN, CONSUMER
from test_junkie_tcms.auth.tokens import new_token
from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import (
    Actor,
    ApiToken,
    Consumer,
    ConsumerProduct,
    Org,
    PairingRequest,
)
from test_junkie_tcms.errors import ProblemError

router = APIRouter(tags=["pairing"])

EXPIRES_IN = timedelta(minutes=10)
INTERVAL = 5
# Consonants only: no vowels to spell words, nothing that reads like 0/O or 1/I.
USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"
LIMIT_PER_MINUTE = 10


def _hash(device_code: str) -> str:
    return hashlib.sha256(device_code.encode()).hexdigest()


def _user_code() -> str:
    letters = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return f"{letters[:4]}-{letters[4:]}"


def normalize_user_code(value: str) -> str:
    letters = "".join(c for c in value.upper() if c.isalnum())
    return f"{letters[:4]}-{letters[4:]}"


def _rate_limit(request: Request) -> str | None:
    """In-process, per client IP: enough for one self-hosted process."""
    ip = request.client.host if request.client else None
    hits = request.app.state.__dict__.setdefault("pair_hits", {})
    now = time.monotonic()
    seen = hits.setdefault(ip, deque())
    while seen and now - seen[0] > 60:
        seen.popleft()
    if len(seen) >= LIMIT_PER_MINUTE:
        raise ProblemError(429, "Too many pairing requests; try again in a minute", error="slow_down")
    seen.append(now)
    return ip


@router.post(
    "/pair",
    status_code=201,
    response_model=PairingCreated,
    **op("pairings_create", None, "consumers", mcp=False),
)
def pairings_create(request: Request, body: PairingIn | None = None, db: Session = Depends(get_db)):
    """No auth: a consumer asks to pair, optionally telling about itself; an admin previews the user
    code on the Consumers screen and approves or denies it."""
    ip = _rate_limit(request)
    device_code = secrets.token_urlsafe(32)
    user_code = _user_code()
    while db.scalar(select(PairingRequest.id).where(PairingRequest.user_code == user_code)):
        user_code = _user_code()
    db.add(
        PairingRequest(
            device_code_hash=_hash(device_code),
            user_code=user_code,
            status="pending",
            expires_at=utcnow() + EXPIRES_IN,
            client_ip=ip,
            machine=body.model_dump() if body else None,
        )
    )
    db.commit()
    return PairingCreated(
        device_code=device_code,
        user_code=user_code,
        verification_uri=f"{request.base_url}consumers/pair",
        expires_in=int(EXPIRES_IN.total_seconds()),
        interval=INTERVAL,
    )


@router.post("/pair/token", response_model=PairingToken, **op("pairings_token", None, "consumers", mcp=False))
def pairings_token(body: PairingTokenIn, db: Session = Depends(get_db)):
    """Poll: 428 until approved, then the token once; 403 once denied; 410 once expired or claimed."""
    row = db.scalar(select(PairingRequest).where(PairingRequest.device_code_hash == _hash(body.device_code)))
    if row is None:
        raise ProblemError(404, "Unknown device code", error="invalid_grant")
    if row.status == "denied":
        raise ProblemError(403, "An admin denied the pairing request", error="access_denied")
    if row.status == "claimed" or aware(row.expires_at) <= utcnow():
        raise ProblemError(410, "The pairing request expired or was already used", error="expired_token")
    if row.status == "pending":
        raise ProblemError(428, "Waiting for an admin to approve the code", error="authorization_pending")
    consumer = db.get(Consumer, row.consumer_id)
    product_ids = sorted(
        db.scalars(select(ConsumerProduct.product_id).where(ConsumerProduct.consumer_id == consumer.id))
    )
    token, prefix, digest = new_token()
    api_token = ApiToken(
        org_id=consumer.org_id,
        actor_id=consumer.actor_id,
        created_by_actor_id=consumer.approved_by_actor_id,
        name=f"consumer {consumer.name}",
        prefix=prefix,
        hash=digest,
        scopes=[CONSUMER],
        product_ids=product_ids,
    )
    db.add(api_token)
    db.flush()
    consumer.token_id = api_token.id
    row.status = "claimed"
    org = db.get(Org, consumer.org_id)
    actor = db.get(Actor, consumer.actor_id)
    ctx = OrgContext(
        org=org,
        actor=actor,
        role=actor.role,
        scopes=frozenset({CONSUMER}),
        principal=Principal(via="api", token=api_token, actor=actor),
    )
    audit.record(db, ctx, "consumer.token_issue", "consumer", consumer.id, {"token_id": api_token.id})
    db.commit()
    return PairingToken(access_token=token, consumer_id=consumer.id, org=org.slug)


@router.post(
    "/orgs/{org}/pair/approve",
    status_code=201,
    response_model=ConsumerOut,
    **op("pairings_approve", ADMIN, "consumers"),
)
def pairings_approve(
    body: PairingApprove,
    ctx: OrgContext = Depends(require_scope(ADMIN)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    row = db.scalar(
        select(PairingRequest).where(
            PairingRequest.user_code == normalize_user_code(body.user_code),
            PairingRequest.status == "pending",
        )
    )
    if row is None:
        raise HTTPException(404, "No pending pairing request with that code")
    if aware(row.expires_at) <= utcnow():
        raise ProblemError(410, "The pairing request expired; start pairing again", error="expired_token")
    check_name_free(db, ctx.org.id, body.name)
    product_ids = check_products(db, ctx, body.product_ids)
    actor = Actor(
        org_id=ctx.org.id,
        kind="agent",
        name=body.name,
        owner_user_id=ctx.actor.user_id or ctx.actor.owner_user_id,
        role="tester",
    )
    db.add(actor)
    db.flush()
    consumer = Consumer(
        org_id=ctx.org.id,
        name=body.name,
        actor_id=actor.id,
        approved_by_actor_id=ctx.actor.id,
        paused_at=None if body.accept_jobs else utcnow(),
    )
    db.add(consumer)
    db.flush()
    db.add_all(ConsumerProduct(org_id=ctx.org.id, consumer_id=consumer.id, product_id=i) for i in product_ids)
    row.org_id = ctx.org.id
    row.consumer_id = consumer.id
    row.status = "approved"
    changes = {"name": body.name, "product_ids": product_ids, "actor_id": actor.id}
    audit.record(db, ctx, "consumer.pair", "consumer", consumer.id, changes)
    db.commit()
    return consumer_out(
        consumer, product_ids, consumer_project_counts(db, [consumer.id])[consumer.id], utcnow()
    )


@router.post("/orgs/{org}/pair/deny", status_code=204, **op("pairings_deny", ADMIN, "consumers"))
def pairings_deny(
    body: PairingDeny,
    ctx: OrgContext = Depends(require_scope(ADMIN)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Refuse a pending request: the machine's next poll gets 403 access_denied."""
    row = _find(db, ctx, body.user_code)
    if row.status != "pending":
        raise ProblemError(409, f"The pairing request is already {row.status}", code="pairing_not_pending")
    row.org_id = ctx.org.id
    row.status = "denied"
    audit.record(
        db, ctx, "pairing.deny", "pairing_request", row.id, {"status": {"from": "pending", "to": "denied"}}
    )
    db.commit()


@router.get(
    "/orgs/{org}/pair/{user_code}",
    response_model=PairingPreview,
    **op("pairings_get", ADMIN, "consumers"),
)
def pairings_get(
    user_code: str, ctx: OrgContext = Depends(require_scope(ADMIN)), db: Session = Depends(get_db)
):
    """What the machine said about itself when it asked to pair, before an admin approves or denies it."""
    row = _find(db, ctx, user_code)
    return PairingPreview(
        user_code=row.user_code, status=row.status, expires_at=row.expires_at, **(row.machine or {})
    )


def _find(db: Session, ctx: OrgContext, user_code: str) -> PairingRequest:
    """A pending request belongs to no org yet; once decided, only its org sees it."""
    row = db.scalar(select(PairingRequest).where(PairingRequest.user_code == normalize_user_code(user_code)))
    if row is None or row.org_id not in (None, ctx.org.id):
        raise HTTPException(404, "No pairing request with that code")
    if row.status == "pending" and aware(row.expires_at) <= utcnow():
        raise ProblemError(410, "The pairing request expired; start pairing again", error="expired_token")
    return row
