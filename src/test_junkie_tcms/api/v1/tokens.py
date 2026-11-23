"""Scoped, revocable API tokens."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.schemas import Page, TokenCreate, TokenCreated, TokenOut
from test_junkie_tcms.auth.deps import OrgContext, effective_role, get_db, get_org_context
from test_junkie_tcms.auth.scopes import ADMIN, ALL_SCOPES, ROLE_SCOPES, TOKENS_SELF
from test_junkie_tcms.auth.tokens import new_token
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import Actor, ApiToken, Product

router = APIRouter(tags=["tokens"])
TOKENS = "/orgs/{org}/tokens"


def _require_own_or_admin(ctx: OrgContext, actor_id: str) -> None:
    if ctx.has(ADMIN):
        return
    if actor_id == ctx.actor.id and ctx.has(TOKENS_SELF):
        return
    raise HTTPException(403, f"Needs scope {ADMIN}, or {TOKENS_SELF} for your own tokens")


def _product_ids(db: Session, ctx: OrgContext, wanted: list[str] | None) -> list[str] | None:
    """Every id must be a product in this org; a limited caller can't mint a wider token."""
    if wanted is None:
        return sorted(ctx.product_ids) if ctx.product_ids is not None else None
    ids = sorted(set(wanted))
    found = set(db.scalars(select(Product.id).where(Product.org_id == ctx.org.id, Product.id.in_(ids))))
    unknown = [i for i in ids if i not in found or not ctx.sees_product(i)]
    if unknown:
        raise HTTPException(422, f"Unknown products: {', '.join(unknown)}")
    return ids


@router.get(TOKENS, response_model=Page[TokenOut], **op("tokens_list", TOKENS_SELF, "admin"))
def tokens_list(
    ctx: OrgContext = Depends(get_org_context),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    query = select(ApiToken).where(ApiToken.org_id == ctx.org.id)
    if not ctx.has(ADMIN):
        _require_own_or_admin(ctx, ctx.actor.id)
        query = query.where(ApiToken.actor_id == ctx.actor.id)
    rows, cursor, total = paginate(db, query, ApiToken.id, params)
    return Page[TokenOut](items=rows, next_cursor=cursor, total=total)


@router.post(
    TOKENS, status_code=201, response_model=TokenCreated, **op("tokens_create", TOKENS_SELF, "admin")
)
def tokens_create(
    body: TokenCreate, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)
):
    actor_id = body.actor_id or ctx.actor.id
    _require_own_or_admin(ctx, actor_id)
    product_ids = _product_ids(db, ctx, body.product_ids)
    target = db.scalar(select(Actor).where(Actor.org_id == ctx.org.id, Actor.id == actor_id))
    if target is None:
        raise HTTPException(404, "Actor not found")
    role = effective_role(db, target)
    if role is None:
        raise HTTPException(422, "That actor is disabled or no longer a member")
    scopes = sorted(set(body.scopes))
    unknown = set(scopes) - ALL_SCOPES
    if unknown:
        raise HTTPException(422, f"Unknown scopes: {', '.join(sorted(unknown))}")
    above_role = set(scopes) - ROLE_SCOPES[role]
    if above_role:
        raise HTTPException(422, f"Scopes above the actor's role ({role}): {', '.join(sorted(above_role))}")
    above_caller = set(scopes) - ctx.scopes
    if above_caller:
        raise HTTPException(422, f"Scopes you don't hold: {', '.join(sorted(above_caller))}")
    if body.expires_at is not None and body.expires_at.tzinfo is None:
        raise HTTPException(422, "expires_at needs a time zone")
    token, prefix, digest = new_token()
    row = ApiToken(
        org_id=ctx.org.id,
        actor_id=target.id,
        created_by_actor_id=ctx.actor.id,
        name=body.name,
        prefix=prefix,
        hash=digest,
        scopes=scopes,
        product_ids=product_ids,
        expires_at=body.expires_at,
    )
    db.add(row)
    db.flush()
    changes = {"actor_id": target.id, "scopes": scopes, "product_ids": product_ids}
    audit.record(db, ctx, "token.create", "api_token", row.id, changes)
    db.commit()
    return TokenCreated(**TokenOut.model_validate(row).model_dump(), token=token)


@router.delete(TOKENS + "/{token_id}", status_code=204, **op("tokens_revoke", TOKENS_SELF, "admin"))
def tokens_revoke(token_id: str, ctx: OrgContext = Depends(get_org_context), db: Session = Depends(get_db)):
    row = db.scalar(select(ApiToken).where(ApiToken.org_id == ctx.org.id, ApiToken.id == token_id))
    if row is None:
        raise HTTPException(404, "Token not found")
    _require_own_or_admin(ctx, row.actor_id)
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        audit.record(db, ctx, "token.revoke", "api_token", row.id)
        db.commit()
    return Response(status_code=204)
