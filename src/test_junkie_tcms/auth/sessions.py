"""Cookie sessions with double-submit CSRF.

`tj_session` = `<session_id>.<secret>` (HttpOnly); `tj_csrf` is readable by the page, which echoes it in
`X-CSRF-Token`. Only HMACs of the secret and the CSRF value are stored.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Response
from sqlalchemy.orm import Session

from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import User, UserSession
from test_junkie_tcms.settings import Settings

SESSION_COOKIE = "tj_session"
CSRF_COOKIE = "tj_csrf"
CSRF_HEADER = "X-CSRF-Token"


def keyed_hash(settings: Settings, value: str) -> str:
    return hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def start_session(
    db: Session, settings: Settings, user: User, ip: str | None, user_agent: str | None
) -> tuple[UserSession, str, str]:
    """Create the session row; return it with the cookie value and the CSRF value."""
    secret = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    row = UserSession(
        user_id=user.id,
        secret_hash=keyed_hash(settings, secret),
        csrf_hash=keyed_hash(settings, csrf),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    db.add(row)
    db.flush()
    return row, f"{row.id}.{secret}", csrf


def find_session(db: Session, settings: Settings, cookie: str) -> UserSession | None:
    session_id, _, secret = cookie.partition(".")
    if not session_id or not secret:
        return None
    row = db.get(UserSession, session_id)
    if row is None or not hmac.compare_digest(row.secret_hash, keyed_hash(settings, secret)):
        return None
    if row.revoked_at is not None or aware(row.expires_at) <= utcnow():
        return None
    return row


def csrf_ok(settings: Settings, row: UserSession, cookie: str | None, header: str | None) -> bool:
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        return False
    return hmac.compare_digest(row.csrf_hash, keyed_hash(settings, header))


def set_cookies(response: Response, settings: Settings, session_cookie: str, csrf: str) -> None:
    max_age = settings.session_ttl_hours * 3600
    secure = not settings.insecure_cookies
    response.set_cookie(
        SESSION_COOKIE, session_cookie, max_age=max_age, httponly=True, secure=secure, samesite="lax"
    )
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=secure, samesite="lax")


def clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
