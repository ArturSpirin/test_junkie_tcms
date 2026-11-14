"""Helpers the catalog routers share: rich text in and out, lookups that respect a token's products."""

import re
from typing import Any

from fastapi import HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_junkie_tcms.api.v1.schemas import DocIn, RichIn, RichMode
from test_junkie_tcms.auth.deps import OrgContext
from test_junkie_tcms.db.models import Feature, Product, Release, TestPlan
from test_junkie_tcms.richtext import RichTextError, doc_to_md, doc_to_text, empty_doc, md_to_doc, validate

KEY = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


def rich_mode(
    rich: RichMode = Query("markdown", description="Rich fields as markdown (default), doc, or both"),
) -> RichMode:
    return rich


def rich_out(doc: dict[str, Any], mode: RichMode) -> str | dict[str, Any]:
    if mode == "doc":
        return doc
    if mode == "both":
        return {"markdown": doc_to_md(doc), "doc": doc}
    return doc_to_md(doc)


def to_doc(field: str, value: RichIn | None) -> dict[str, Any]:
    """Turn a {markdown} or {doc} body field into a validated doc; 422 naming the field and path."""
    if value is None:
        return empty_doc()
    try:
        if isinstance(value, DocIn):
            validate(value.doc)
            return value.doc
        return md_to_doc(value.markdown)
    except RichTextError as e:
        raise HTTPException(422, f"{field}: {e}") from e


def set_rich(row: Any, field: str, value: RichIn, changes: dict[str, list]) -> None:
    """Set a rich field and its *_text, and log the Markdown before and after when it changed."""
    doc = to_doc(field, value)
    old = getattr(row, field)
    if doc != old:
        changes[field] = [doc_to_md(old), doc_to_md(doc)]
        setattr(row, field, doc)
        setattr(row, f"{field}_text", doc_to_text(doc))


def get_product(db: Session, ctx: OrgContext, ref: str) -> Product:
    """A product by id or key; 404 when it isn't in the org or the token can't see it."""
    column = Product.key if KEY.match(ref) else Product.id
    product = db.scalar(select(Product).where(Product.org_id == ctx.org.id, column == ref))
    if product is None or not ctx.sees_product(product.id):
        raise HTTPException(404, "Product not found")
    return product


def _get(db: Session, ctx: OrgContext, model: type, id_: str, label: str):
    row = db.scalar(select(model).where(model.org_id == ctx.org.id, model.id == id_))
    if row is None or not ctx.sees_product(row.product_id):
        raise HTTPException(404, f"{label} not found")
    return row


def get_feature(db: Session, ctx: OrgContext, id_: str) -> Feature:
    return _get(db, ctx, Feature, id_, "Feature")


def get_release(db: Session, ctx: OrgContext, id_: str) -> Release:
    return _get(db, ctx, Release, id_, "Release")


def get_plan(db: Session, ctx: OrgContext, id_: str) -> TestPlan:
    return _get(db, ctx, TestPlan, id_, "Plan")


def require_active_product(db: Session, product_id: str) -> None:
    if db.get(Product, product_id).archived_at is not None:
        raise HTTPException(409, "Product is archived")


def product_features(db: Session, ctx: OrgContext, product_id: str, ids: list[str]) -> list[Feature]:
    """Features the body names for a link; each must be in this product (422) and not archived (409).

    A feature in another product the token can't see gets the same 422 as an unknown id, so a
    limited token learns nothing about it.
    """
    wanted = list(dict.fromkeys(ids))
    rows = {
        f.id: f
        for f in db.scalars(select(Feature).where(Feature.org_id == ctx.org.id, Feature.id.in_(wanted)))
        if f.product_id == product_id
    }
    missing = [i for i in wanted if i not in rows]
    if missing:
        raise HTTPException(422, f"Not features of this product: {', '.join(missing)}")
    archived = [i for i in wanted if rows[i].archived_at is not None]
    if archived:
        raise HTTPException(409, f"Features are archived: {', '.join(archived)}")
    return [rows[i] for i in wanted]
