"""Features: a tree under each product, ordered by position among siblings."""

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.idempotency import Idem, idempotency
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.v1.catalog import (
    get_feature,
    get_product,
    require_active_product,
    rich_mode,
    rich_out,
    set_rich,
    to_doc,
)
from test_junkie_tcms.api.v1.schemas import (
    ActorRef,
    FeatureCreate,
    FeatureMove,
    FeatureNode,
    FeatureOut,
    FeatureTree,
    FeatureUpdate,
    RichMode,
)
from test_junkie_tcms.auth.deps import OrgContext, get_db, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_CATALOG
from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import Actor, AuditEvent, Feature
from test_junkie_tcms.richtext import doc_to_md, doc_to_text

router = APIRouter(tags=["catalog"])
FEATURES = "/orgs/{org}/products/{product}/features"
FEATURE = "/orgs/{org}/features/{id}"
MAX_TREE = 2000


def feature_out(f: Feature, mode: RichMode) -> FeatureOut:
    return FeatureOut(
        id=f.id,
        product_id=f.product_id,
        parent_id=f.parent_id,
        name=f.name,
        description=rich_out(f.description, mode),
        owner_actor_id=f.owner_actor_id,
        position=f.position,
        archived_at=f.archived_at,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _order(f: Feature) -> tuple[int, str]:
    return f.position, f.id


def _siblings(db: Session, product_id: str, parent_id: str | None, org_id: str) -> list[Feature]:
    same_parent = Feature.parent_id.is_(None) if parent_id is None else Feature.parent_id == parent_id
    rows = db.scalars(
        select(Feature).where(Feature.org_id == org_id, Feature.product_id == product_id, same_parent)
    )
    return sorted(rows, key=_order)


def _renumber(rows: list[Feature]) -> None:
    for i, row in enumerate(rows):
        if row.position != i:
            row.position = i


def _parent(db: Session, ctx: OrgContext, product_id: str, parent_id: str | None) -> Feature | None:
    """The parent a body names: in the same product (422) and not archived (409)."""
    if parent_id is None:
        return None
    parent = db.scalar(select(Feature).where(Feature.org_id == ctx.org.id, Feature.id == parent_id))
    if parent is None or parent.product_id != product_id:
        raise HTTPException(422, "parent_id is not a feature of this product")
    if parent.archived_at is not None:
        raise HTTPException(409, "Parent feature is archived")
    return parent


def _check_owner(db: Session, ctx: OrgContext, actor_id: str | None) -> None:
    if actor_id is not None and not db.scalar(
        select(Actor.id).where(Actor.org_id == ctx.org.id, Actor.id == actor_id)
    ):
        raise HTTPException(422, "owner_actor_id is not an actor in this org")


@router.get(FEATURES, response_model=FeatureTree, **op("features_list", READ, "catalog"))
def features_list(
    product: str,
    include_archived: bool = Query(False),
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    query = select(Feature).where(Feature.org_id == ctx.org.id, Feature.product_id == p.id)
    if not include_archived:
        query = query.where(Feature.archived_at.is_(None))
    rows = list(db.scalars(query.limit(MAX_TREE + 1)))
    if len(rows) > MAX_TREE:
        raise HTTPException(422, f"The feature tree has more than {MAX_TREE} nodes")
    children: dict[str | None, list[Feature]] = defaultdict(list)
    ids = {f.id for f in rows}
    for f in rows:
        children[f.parent_id if f.parent_id in ids else None].append(f)

    last = _last_edits(db, ctx.org.id, p.id)

    def node(f: Feature) -> FeatureNode:
        data = feature_out(f, mode).model_dump()
        if f.id in last:
            data["updated_at"], data["updated_by"] = last[f.id]
        return FeatureNode(**data, children=build(f.id))

    def build(parent_id: str | None) -> list[FeatureNode]:
        return [node(f) for f in sorted(children[parent_id], key=_order)]

    return FeatureTree(items=build(None))


def _last_edits(db: Session, org_id: str, product_id: str) -> dict[str, tuple[datetime, ActorRef]]:
    """Each feature's latest `feature` audit event: its time and actor.

    Archiving audits only the archived root, so its descendants keep their older last editor. Release
    membership edits are audited on the release, so they don't count as a feature edit."""
    latest = (
        select(
            AuditEvent.entity_id,
            AuditEvent.created_at,
            AuditEvent.actor_id,
            func.row_number()
            .over(
                partition_by=AuditEvent.entity_id,
                order_by=(AuditEvent.created_at.desc(), AuditEvent.id.desc()),
            )
            .label("rn"),
        )
        .join(Feature, and_(Feature.org_id == AuditEvent.org_id, Feature.id == AuditEvent.entity_id))
        .where(
            AuditEvent.org_id == org_id, AuditEvent.entity_type == "feature", Feature.product_id == product_id
        )
        .subquery()
    )
    rows = db.execute(
        select(latest.c.entity_id, latest.c.created_at, Actor.id, Actor.name, Actor.kind)
        .join(Actor, and_(Actor.org_id == org_id, Actor.id == latest.c.actor_id))
        .where(latest.c.rn == 1)
    )
    return {
        entity_id: (aware(at), ActorRef(id=actor_id, name=name, kind=kind))
        for entity_id, at, actor_id, name, kind in rows
    }


@router.post(
    FEATURES, status_code=201, response_model=FeatureOut, **op("features_create", WRITE_CATALOG, "catalog")
)
def features_create(
    product: str,
    body: FeatureCreate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    _parent(db, ctx, p.id, body.parent_id)
    _check_owner(db, ctx, body.owner_actor_id)
    doc = to_doc("description", body.description)
    f = Feature(
        org_id=ctx.org.id,
        product_id=p.id,
        parent_id=body.parent_id,
        name=body.name,
        description=doc,
        description_text=doc_to_text(doc),
        owner_actor_id=body.owner_actor_id,
        position=len(_siblings(db, p.id, body.parent_id, ctx.org.id)),
    )
    db.add(f)
    db.flush()
    changes = {
        "name": [None, f.name],
        "parent_id": [None, f.parent_id],
        "description": [None, doc_to_md(doc)],
        "owner_actor_id": [None, f.owner_actor_id],
    }
    audit.record(db, ctx, "feature.create", "feature", f.id, changes)
    db.commit()
    return feature_out(f, mode)


@router.get(FEATURE, response_model=FeatureOut, **op("features_get", READ, "catalog"))
def features_get(
    id: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(READ)),
    db: Session = Depends(get_db),
):
    return feature_out(get_feature(db, ctx, id), mode)


@router.patch(FEATURE, response_model=FeatureOut, **op("features_update", WRITE_CATALOG, "catalog"))
def features_update(
    id: str,
    body: FeatureUpdate,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    db: Session = Depends(get_db),
):
    f = get_feature(db, ctx, id)
    changes: dict[str, list] = {}
    if body.name is not None and body.name != f.name:
        changes["name"] = [f.name, body.name]
        f.name = body.name
    if body.description is not None:
        set_rich(f, "description", body.description, changes)
    if "owner_actor_id" in body.model_fields_set and body.owner_actor_id != f.owner_actor_id:
        _check_owner(db, ctx, body.owner_actor_id)
        changes["owner_actor_id"] = [f.owner_actor_id, body.owner_actor_id]
        f.owner_actor_id = body.owner_actor_id
    if changes:
        audit.record(db, ctx, "feature.update", "feature", f.id, changes)
        db.commit()
    return feature_out(f, mode)


@router.post(FEATURE + "/move", response_model=FeatureOut, **op("features_move", WRITE_CATALOG, "catalog"))
def features_move(
    id: str,
    body: FeatureMove,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    f = get_feature(db, ctx, id)
    parent = _parent(db, ctx, f.product_id, body.parent_id)
    while parent is not None:
        if parent.id == f.id:
            raise HTTPException(409, "A feature can't move inside its own subtree")
        parent = db.get(Feature, parent.parent_id) if parent.parent_id else None
    before = [f.parent_id, f.position]
    old = [s for s in _siblings(db, f.product_id, f.parent_id, ctx.org.id) if s.id != f.id]
    new = [s for s in _siblings(db, f.product_id, body.parent_id, ctx.org.id) if s.id != f.id]
    new.insert(min(body.position, len(new)), f)
    f.parent_id = body.parent_id
    _renumber(old)
    _renumber(new)
    after = [f.parent_id, f.position]
    if after != before:
        changes = {"parent_id": [before[0], after[0]], "position": [before[1], after[1]]}
        audit.record(db, ctx, "feature.move", "feature", f.id, changes)
    db.commit()
    return feature_out(f, mode)


@router.post(
    FEATURE + "/archive", response_model=FeatureOut, **op("features_archive", WRITE_CATALOG, "catalog")
)
def features_archive(
    id: str,
    mode: RichMode = Depends(rich_mode),
    ctx: OrgContext = Depends(require_scope(WRITE_CATALOG)),
    idem: Idem = Depends(idempotency),
    db: Session = Depends(get_db),
):
    """Archives the feature and every feature under it."""
    f = get_feature(db, ctx, id)
    rows = list(
        db.scalars(select(Feature).where(Feature.org_id == ctx.org.id, Feature.product_id == f.product_id))
    )
    children: dict[str | None, list[Feature]] = defaultdict(list)
    for row in rows:
        children[row.parent_id].append(row)
    now, archived, todo = utcnow(), [], [f]
    while todo:
        row = todo.pop()
        todo.extend(children[row.id])
        if row.archived_at is None:
            row.archived_at = now
            archived.append(row.id)
    if archived:
        audit.record(db, ctx, "feature.archive", "feature", f.id, {"archived": [None, sorted(archived)]})
    db.commit()  # a no-op commits too, so an Idempotency-Key replays it
    return feature_out(f, mode)
