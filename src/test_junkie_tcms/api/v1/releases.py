"""Releases: owned by a product, listing the features they affect."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.pagination import PageParams, page_params, paginate
from test_junkie_tcms.api.v1.catalog import (
    get_product,
    get_release,
    product_features,
    require_active_product,
    rich_mode,
    rich_out,
    set_rich,
    to_doc,
)
from test_junkie_tcms.api.v1.schemas import (
    Page,
    ReleaseCreate,
    ReleaseFeaturesIn,
    ReleaseOut,
    ReleaseUpdate,
    RichMode,
)
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_CATALOG
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import Release, ReleaseFeature
from test_junkie_tcms.richtext import doc_to_md, doc_to_text

router = APIRouter(tags=["catalog"])
RELEASES = "/orgs/{org}/products/{product}/releases"
RELEASE = "/orgs/{org}/releases/{id}"


def _feature_ids(db: Session, r: Release) -> list[str]:
    return sorted(
        db.scalars(
            select(ReleaseFeature.feature_id).where(
                ReleaseFeature.org_id == r.org_id, ReleaseFeature.release_id == r.id
            )
        )
    )


def release_out(db: Session, r: Release, mode: RichMode) -> ReleaseOut:
    return ReleaseOut(
        id=r.id,
        product_id=r.product_id,
        version=r.version,
        name=r.name,
        status=r.status,
        target_date=r.target_date,
        released_at=r.released_at,
        notes=rich_out(r.notes, mode),
        feature_ids=_feature_ids(db, r),
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _version_free(db: Session, ctx: OrgContext, product_id: str, version: str) -> None:
    taken = db.scalar(
        select(Release.id).where(
            Release.org_id == ctx.org.id, Release.product_id == product_id, Release.version == version
        )
    )
    if taken:
        raise HTTPException(409, f"Version {version} already exists for this product")


@router.get(RELEASES, response_model=Page[ReleaseOut], **op("releases_list", READ, "catalog"))
def releases_list(
    product: str,
    params: PageParams = Depends(page_params),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    query = select(Release).where(Release.org_id == ctx.org.id, Release.product_id == p.id)
    rows, cursor = paginate(db, query, Release.id, params)
    return Page[ReleaseOut](items=[release_out(db, r, mode) for r in rows], next_cursor=cursor)


@router.post(
    RELEASES, status_code=201, response_model=ReleaseOut, **op("releases_create", WRITE_CATALOG, "catalog")
)
def releases_create(
    product: str,
    body: ReleaseCreate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    _version_free(db, ctx, p.id, body.version)
    doc = to_doc("notes", body.notes)
    released_at = body.released_at or (utcnow() if body.status == "released" else None)
    r = Release(
        org_id=ctx.org.id,
        product_id=p.id,
        version=body.version,
        name=body.name,
        status=body.status,
        target_date=body.target_date,
        released_at=released_at,
        notes=doc,
        notes_text=doc_to_text(doc),
    )
    db.add(r)
    db.flush()
    changes = {
        "version": [None, r.version],
        "name": [None, r.name],
        "status": [None, r.status],
        "notes": [None, doc_to_md(doc)],
    }
    audit.record(db, ctx, "release.create", "release", r.id, changes)
    db.commit()
    return release_out(db, r, mode)


@router.get(RELEASE, response_model=ReleaseOut, **op("releases_get", READ, "catalog"))
def releases_get(
    id: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    return release_out(db, get_release(db, ctx, id), mode)


@router.patch(RELEASE, response_model=ReleaseOut, **op("releases_update", WRITE_CATALOG, "catalog"))
def releases_update(
    id: str,
    body: ReleaseUpdate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    db: Session = Depends(get_db),
):
    r = get_release(db, ctx, id)
    changes: dict[str, list] = {}
    if body.version is not None and body.version != r.version:
        _version_free(db, ctx, r.product_id, body.version)
    for field in ("version", "name", "status"):
        value = getattr(body, field)
        if value is not None and value != getattr(r, field):
            changes[field] = [getattr(r, field), value]
            setattr(r, field, value)
    for field in ("target_date", "released_at"):
        value = getattr(body, field)
        if field in body.model_fields_set and value != getattr(r, field):
            changes[field] = [str(getattr(r, field) or "") or None, str(value or "") or None]
            setattr(r, field, value)
    if r.status == "released" and r.released_at is None:
        r.released_at = utcnow()
        changes["released_at"] = [None, r.released_at.isoformat()]
    if body.notes is not None:
        set_rich(r, "notes", body.notes, changes)
    if changes:
        audit.record(db, ctx, "release.update", "release", r.id, changes)
        db.commit()
    return release_out(db, r, mode)


@router.put(
    RELEASE + "/features", response_model=ReleaseOut, **op("releases_set_features", WRITE_CATALOG, "catalog")
)
def releases_set_features(
    id: str,
    body: ReleaseFeaturesIn,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    db: Session = Depends(get_db),
):
    """Replaces the features the release affects. Each must be an active feature of the release's product."""
    r = get_release(db, ctx, id)
    before = _feature_ids(db, r)
    after = sorted(f.id for f in product_features(db, ctx, r.product_id, body.feature_ids))
    if after != before:
        db.execute(
            delete(ReleaseFeature).where(ReleaseFeature.org_id == r.org_id, ReleaseFeature.release_id == r.id)
        )
        db.add_all(ReleaseFeature(org_id=r.org_id, release_id=r.id, feature_id=f) for f in after)
        audit.record(db, ctx, "release.set_features", "release", r.id, {"feature_ids": [before, after]})
        db.commit()
    return release_out(db, r, mode)
