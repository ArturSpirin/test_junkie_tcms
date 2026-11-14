from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.v1.schemas import LoginIn, MeOrg, MeOut
from test_junkie_tcms.auth import sessions
from test_junkie_tcms.auth.deps import Principal, effective_role, get_db, get_principal, get_settings
from test_junkie_tcms.auth.passwords import verify_password
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import Actor, Org, User
from test_junkie_tcms.settings import Settings

router = APIRouter(tags=["auth"])


def _me(db: Session, principal: Principal) -> MeOut:
    if principal.token is not None:
        actor = principal.actor
        org = db.get(Org, actor.org_id)
        role = effective_role(db, actor)
        return MeOut(
            via=principal.via,
            actor_id=actor.id,
            token_id=principal.token.id,
            name=actor.name,
            orgs=[MeOrg(slug=org.slug, name=org.name, role=role)] if role else [],
        )
    user = principal.user
    orgs = []
    actors = db.scalars(select(Actor).where(Actor.kind == "user", Actor.user_id == user.id))
    for actor in actors:
        role = effective_role(db, actor)
        if role:
            org = db.get(Org, actor.org_id)
            orgs.append(MeOrg(slug=org.slug, name=org.name, role=role))
    return MeOut(via=principal.via, user_id=user.id, email=user.email, name=user.name, orgs=orgs)


@router.post("/auth/login", response_model=MeOut, **op("auth_login", None, "auth", mcp=False))
def auth_login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MeOut:
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    # Always run argon2, even for an unknown email, so timing doesn't reveal which emails exist.
    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not user.is_active or not password_ok:
        raise HTTPException(401, "Wrong email or password")
    row, cookie, csrf = sessions.start_session(
        db, settings, user, request.client.host if request.client else None, request.headers.get("user-agent")
    )
    db.commit()
    sessions.set_cookies(response, settings, cookie, csrf)
    return _me(db, Principal(via="ui", user=user, session=row))


@router.post("/auth/logout", status_code=204, **op("auth_logout", None, "auth", mcp=False))
def auth_logout(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> Response:
    if principal.session is None:
        raise HTTPException(400, "Logout ends a cookie session; revoke a token with tokens_revoke")
    principal.session.revoked_at = utcnow()
    db.commit()
    response = Response(status_code=204)
    sessions.clear_cookies(response)
    return response


@router.get("/me", response_model=MeOut, **op("me_get", None, "auth"))
def me_get(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> MeOut:
    return _me(db, principal)
