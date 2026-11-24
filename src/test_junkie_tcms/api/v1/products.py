"""Products: the top of the catalog. Addressed by id or key."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.catalog import (
    get_product,
    name_filter,
    name_q,
    product_counts,
    rich_mode,
    rich_out,
    set_rich,
    to_doc,
)
from test_junkie_tcms.api.v1.features import copy_tree
from test_junkie_tcms.api.v1.schemas import Page, ProductCreate, ProductOut, ProductUpdate, RichMode
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_CATALOG
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import Actor, Membership, Product
from test_junkie_tcms.errors import ProblemError
from test_junkie_tcms.richtext import doc_to_md, doc_to_text

router = APIRouter(tags=["catalog"])
PRODUCTS = "/orgs/{org}/products"
PRODUCT = PRODUCTS + "/{product}"


def _check_owner(db: Session, ctx: OrgContext, actor_id: str | None) -> None:
    """A product's owner is a person: an enabled user actor whose membership in this org is live."""
    if actor_id is None:
        return
    owner = db.scalar(
        select(Actor.id)
        .join(Membership, and_(Membership.org_id == Actor.org_id, Membership.user_id == Actor.user_id))
        .where(
            Actor.org_id == ctx.org.id,
            Actor.id == actor_id,
            Actor.kind == "user",
            Actor.disabled_at.is_(None),
            Membership.removed_at.is_(None),
        )
    )
    if owner is None:
        raise ProblemError(422, "owner_actor_id is not an active member of this org", code="owner_not_member")


def product_out(db: Session, p: Product, mode: RichMode, counts: tuple[int, int] | None = None) -> ProductOut:
    features, cases = counts or product_counts(db, p.org_id, [p.id])[p.id]
    return ProductOut(
        id=p.id,
        key=p.key,
        name=p.name,
        description=rich_out(p.description, mode),
        owner_actor_id=p.owner_actor_id,
        feature_count=features,
        case_count=cases,
        archived_at=p.archived_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get(PRODUCTS, response_model=Page[ProductOut], **op("products_list", READ, "catalog"))
def products_list(
    include_archived: bool = Query(False),
    q: str | None = name_q(),
    params: PageParams = Depends(page_params),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    query = select(Product).where(Product.org_id == ctx.org.id)
    if not include_archived:
        query = query.where(Product.archived_at.is_(None))
    if ctx.product_ids is not None:
        query = query.where(Product.id.in_(ctx.product_ids))
    query = name_filter(query, q, Product.name)
    rows, cursor, total = paginate(db, query, Product.id, params)
    counts = product_counts(db, ctx.org.id, [p.id for p in rows])
    items = [product_out(db, p, mode, counts[p.id]) for p in rows]
    return Page[ProductOut](items=items, next_cursor=cursor, total=total)


@router.post(
    PRODUCTS, status_code=201, response_model=ProductOut, **op("products_create", WRITE_CATALOG, "catalog")
)
def products_create(
    body: ProductCreate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    if ctx.product_ids is not None:
        raise HTTPException(403, "A token limited to some products can't create one")
    if db.scalar(select(Product.id).where(Product.org_id == ctx.org.id, Product.key == body.key)):
        raise HTTPException(409, f"Product key {body.key} is taken")
    _check_owner(db, ctx, body.owner_actor_id)
    # get_product is org-scoped, so a product in another org is a 404 like any unknown one.
    source = get_product(db, ctx, body.copy_features_from) if body.copy_features_from else None
    doc = to_doc("description", body.description)
    p = Product(
        org_id=ctx.org.id,
        key=body.key,
        name=body.name,
        description=doc,
        description_text=doc_to_text(doc),
        owner_actor_id=body.owner_actor_id,
    )
    db.add(p)
    db.flush()
    changes = {"key": [None, p.key], "name": [None, p.name], "description": [None, doc_to_md(doc)]}
    if p.owner_actor_id:
        changes["owner_actor_id"] = [None, p.owner_actor_id]
    if source is not None:
        changes["copied_features_from"] = [None, source.id]
        changes["features_copied"] = [None, copy_tree(db, ctx.org.id, source.id, p.id)]
    audit.record(db, ctx, "product.create", "product", p.id, changes)
    db.commit()
    return product_out(db, p, mode)


@router.get(PRODUCT, response_model=ProductOut, **op("products_get", READ, "catalog"))
def products_get(
    product: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    return product_out(db, get_product(db, ctx, product), mode)


@router.patch(PRODUCT, response_model=ProductOut, **op("products_update", WRITE_CATALOG, "catalog"))
def products_update(
    product: str,
    body: ProductUpdate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    changes: dict[str, list] = {}
    if body.name is not None and body.name != p.name:
        changes["name"] = [p.name, body.name]
        p.name = body.name
    if body.description is not None:
        set_rich(p, "description", body.description, changes)
    if "owner_actor_id" in body.model_fields_set and body.owner_actor_id != p.owner_actor_id:
        _check_owner(db, ctx, body.owner_actor_id)
        changes["owner_actor_id"] = [p.owner_actor_id, body.owner_actor_id]
        p.owner_actor_id = body.owner_actor_id
    if changes:
        audit.record(db, ctx, "product.update", "product", p.id, changes)
        db.commit()
    return product_out(db, p, mode)


@router.post(
    PRODUCT + "/archive", response_model=ProductOut, **op("products_archive", WRITE_CATALOG, "catalog")
)
def products_archive(
    product: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    if p.archived_at is None:
        p.archived_at = utcnow()
        audit.record(db, ctx, "product.archive", "product", p.id)
    db.commit()  # a no-op commits too, so an Idempotency-Key replays it
    return product_out(db, p, mode)
