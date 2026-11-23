"""Case search (T6): text and tags over each case's current version, across the products a caller sees."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.cases import case_key, subtree
from test_junkie_tcms.api.v1.catalog import get_feature, get_product
from test_junkie_tcms.api.v1.report_schemas import SearchHit
from test_junkie_tcms.api.v1.schemas import Page
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ
from test_junkie_tcms.db.models import CaseVersion, CaseVersionTag, Product, Tag, TestCase

router = APIRouter(tags=["cases"])

TEXT_FIELDS = (("title", "title_text"), ("preconditions", "preconditions_text"), ("steps", "steps_text"))


@router.get("/orgs/{org}/search", response_model=Page[SearchHit], **op("search", READ, "cases"))
def search(
    q: str | None = Query(
        None, max_length=200, description="Case-insensitive text in the title, preconditions or steps"
    ),
    tag: list[str] = Query([], description="Repeatable; a case must have every tag"),
    product: str | None = Query(None, description="A product id or key"),
    feature: str | None = Query(None, description="A feature id; its subtree is searched"),
    include_archived: bool = Query(False),
    params: PageParams = Depends(page_params),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    """Cases whose current version matches `q` and has every `tag`. Needs `q` or `tag`."""
    text = (q or "").strip().lower()
    tags = {t.strip().lower() for t in tag if t.strip()}
    if not text and not tags:
        raise HTTPException(422, "Give q or tag")
    current = and_(
        CaseVersion.org_id == TestCase.org_id,
        CaseVersion.case_id == TestCase.id,
        CaseVersion.version == TestCase.current_version,
    )
    query = select(TestCase).join(CaseVersion, current).where(TestCase.org_id == ctx.org.id)
    if ctx.product_ids is not None:
        query = query.where(TestCase.product_id.in_(ctx.product_ids))
    if product is not None:
        query = query.where(TestCase.product_id == get_product(db, ctx, product).id)
    if feature is not None:
        f = get_feature(db, ctx, feature)
        query = query.where(TestCase.feature_id.in_(subtree(db, ctx.org.id, f.product_id, [f.id])))
    if not include_archived:
        query = query.where(TestCase.archived_at.is_(None))
    if text:
        query = query.where(
            or_(
                *(
                    func.lower(getattr(CaseVersion, col)).contains(text, autoescape=True)
                    for _, col in TEXT_FIELDS
                )
            )
        )
    for name in tags:
        query = query.where(
            select(CaseVersionTag.id)
            .join(Tag, Tag.id == CaseVersionTag.tag_id)
            .where(CaseVersionTag.case_version_id == CaseVersion.id, Tag.name == name)
            .exists()
        )
    rows, cursor, total = paginate(db, query, TestCase.id, params)
    versions = {
        v.case_id: v
        for v in db.scalars(
            select(CaseVersion).join(TestCase, current).where(TestCase.id.in_([c.id for c in rows]))
        )
    }
    products = {
        p.id: p for p in db.scalars(select(Product).where(Product.id.in_({c.product_id for c in rows})))
    }
    items = []
    for c in rows:
        v = versions[c.id]
        matched = [name for name, col in TEXT_FIELDS if text and text in (getattr(v, col) or "").lower()]
        items.append(
            SearchHit(
                id=c.id,
                key=case_key(products[c.product_id], c),
                product_id=c.product_id,
                feature_id=c.feature_id,
                title=v.title,
                current_version=c.current_version,
                matched_in=matched,
            )
        )
    return Page[SearchHit](items=items, next_cursor=cursor, total=total)
