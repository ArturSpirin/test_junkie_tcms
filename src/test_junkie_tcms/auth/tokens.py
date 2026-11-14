"""API tokens: `tjt_<prefix8>_<secret>`, stored as the SHA-256 of the whole token."""

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import Actor, ApiToken

_TOKEN_RE = re.compile(r"^tjt_([0-9a-f]{8})_([A-Za-z0-9_-]+)$")
LAST_USED_EVERY = timedelta(minutes=1)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str, str]:
    """Return (token, prefix, hash). The token is shown once and never stored."""
    prefix = secrets.token_hex(4)
    token = f"tjt_{prefix}_{secrets.token_urlsafe(24)}"
    return token, prefix, token_hash(token)


def authenticate_token(db: Session, token: str) -> tuple[ApiToken, Actor] | None:
    match = _TOKEN_RE.match(token)
    if not match:
        return None
    row = db.scalar(select(ApiToken).where(ApiToken.prefix == match.group(1)))
    if row is None or not hmac.compare_digest(row.hash, token_hash(token)):
        return None
    now = utcnow()
    if row.revoked_at is not None:
        return None
    if row.expires_at is not None and aware(row.expires_at) <= now:
        return None
    actor = db.get(Actor, row.actor_id)
    if actor is None or actor.disabled_at is not None:
        return None
    if row.last_used_at is None or now - aware(row.last_used_at) >= LAST_USED_EVERY:
        row.last_used_at = now
        db.commit()
    return row, actor
