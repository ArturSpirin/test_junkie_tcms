"""Products: the top of the catalog. Addressed by id or key."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.catalog import get_product, rich_mode, rich_out, set_rich, to_doc
from test_junkie_tcms.api.v1.schemas import Page, ProductCreate, ProductOut, ProductUpdate, RichMode
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_CATALOG
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import Product
from test_junkie_tcms.richtext import doc_to_md, doc_to_text

router = APIRouter(tags=["catalog"])
PRODUCTS = "/orgs/{org}/products"
PRODUCT = PRODUCTS + "/{product}"


def product_out(p: Product, mode: RichMode) -> ProductOut:
    return ProductOut(
        id=p.id,
        key=p.key,
        name=p.name,
        description=rich_out(p.description, mode),
        archived_at=p.archived_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get(PRODUCTS, response_model=Page[ProductOut], **op("products_list", READ, "catalog"))
def products_list(
    include_archived: bool = Query(False),
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
    rows, cursor = paginate(db, query, Product.id, params)
    return Page[ProductOut](items=[product_out(p, mode) for p in rows], next_cursor=cursor)


@router.post(
    PRODUCTS, status_code=201, response_model=ProductOut, **op("products_create", WRITE_CATALOG, "catalog")
)
def products_create(
    body: ProductCreate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    db: Session = Depends(get_db),
):
    if ctx.product_ids is not None:
        raise HTTPException(403, "A token limited to some products can't create one")
    if db.scalar(select(Product.id).where(Product.org_id == ctx.org.id, Product.key == body.key)):
        raise HTTPException(409, f"Product key {body.key} is taken")
    doc = to_doc("description", body.description)
    p = Product(
        org_id=ctx.org.id, key=body.key, name=body.name, description=doc, description_text=doc_to_text(doc)
    )
    db.add(p)
    db.flush()
    changes = {"key": [None, p.key], "name": [None, p.name], "description": [None, doc_to_md(doc)]}
    audit.record(db, ctx, "product.create", "product", p.id, changes)
    db.commit()
    return product_out(p, mode)


@router.get(PRODUCT, response_model=ProductOut, **op("products_get", READ, "catalog"))
def products_get(
    product: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    return product_out(get_product(db, ctx, product), mode)


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
    if changes:
        audit.record(db, ctx, "product.update", "product", p.id, changes)
        db.commit()
    return product_out(p, mode)


@router.post(
    PRODUCT + "/archive", response_model=ProductOut, **op("products_archive", WRITE_CATALOG, "catalog")
)
def products_archive(
    product: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    if p.archived_at is None:
        p.archived_at = utcnow()
        audit.record(db, ctx, "product.archive", "product", p.id)
        db.commit()
    return product_out(p, mode)
