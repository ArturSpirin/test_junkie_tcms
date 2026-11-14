"""Attachments: files a result points at, deduplicated by content within a product."""

import base64
import binascii
import re
from collections.abc import AsyncIterator
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_junkie_tcms import audit
from test_junkie_tcms.api.operations import op
from test_junkie_tcms.api.v1.catalog import _get, get_product, require_active_product
from test_junkie_tcms.api.v1.execution_schemas import AttachmentBase64In, AttachmentOut
from test_junkie_tcms.auth.deps import OrgContext, get_db, get_settings, require_scope
from test_junkie_tcms.auth.scopes import READ, WRITE_EXECUTION
from test_junkie_tcms.db.models import Attachment
from test_junkie_tcms.storage import LocalStorage, Storage, Stored, TooLarge, one_chunk

router = APIRouter(tags=["execution"])
UPLOADS = "/orgs/{org}/products/{product}/attachments"
BASE64_MAX_BYTES = 5 * 1024 * 1024
MIME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,62}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,62}$")
# Served with their own type; anything else downloads as application/octet-stream.
INLINE_TYPES = {"application/pdf", "text/plain", "application/json", "application/zip"}
RAW_UPLOAD = op("attachments_upload", WRITE_EXECUTION, "execution", mcp=False)
RAW_UPLOAD["openapi_extra"]["requestBody"] = {
    "required": True,
    "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
}


def storage(request: Request) -> Storage:
    return LocalStorage(get_settings(request).attachments_dir)


def clean_filename(name: str) -> str:
    base = re.split(r"[\\/]", name)[-1]
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    if not base or base in {".", ".."}:
        raise HTTPException(422, "filename is empty")
    return base[:255]


def clean_mime(mime: str | None) -> str:
    mime = (mime or "application/octet-stream").split(";")[0].strip().lower()
    if not MIME.match(mime):
        raise HTTPException(422, "mime must look like type/subtype")
    return mime


def served_type(mime: str) -> str:
    if (mime.startswith("image/") and mime != "image/svg+xml") or mime in INLINE_TYPES:
        return mime
    return "application/octet-stream"


def find_existing(db: Session, org_id: str, product_id: str, sha256: str, filename: str) -> Attachment | None:
    return db.scalar(
        select(Attachment).where(
            Attachment.org_id == org_id,
            Attachment.product_id == product_id,
            Attachment.sha256 == sha256,
            Attachment.filename == filename,
        )
    )


def save(
    db: Session,
    ctx: OrgContext,
    product_id: str,
    stored: Stored,
    filename: str,
    mime: str,
    response: Response,
) -> Attachment:
    """The row for this content and name: 201 when new, 200 when it is already there."""

    def existing() -> Attachment | None:
        return find_existing(db, ctx.org.id, product_id, stored.sha256, filename)

    found = existing()
    if found is not None:
        response.status_code = 200
        return found
    row = Attachment(
        org_id=ctx.org.id,
        product_id=product_id,
        sha256=stored.sha256,
        filename=filename,
        mime=mime,
        size=stored.size,
        storage_key=stored.key,
        created_by_actor_id=ctx.actor.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # The same file won a race between our lookup and insert. The upload has written nothing else in
        # this transaction, so roll it all back and return the winner's row. Caught here, before the app's
        # IntegrityError handler would turn it into a 409.
        db.rollback()
        found = existing()
        if found is None:
            raise
        response.status_code = 200
        return found
    changes = {"filename": [None, filename], "sha256": [None, stored.sha256], "size": [None, stored.size]}
    audit.record(db, ctx, "attachment.upload", "attachment", row.id, changes)
    db.commit()
    response.status_code = 201
    return row


async def _store(request: Request, org_id: str, chunks: AsyncIterator[bytes], max_bytes: int) -> Stored:
    try:
        return await storage(request).put(org_id, chunks, max_bytes)
    except TooLarge:
        raise HTTPException(413, f"The file is over {max_bytes} bytes") from None


@router.post(
    UPLOADS,
    status_code=201,
    response_model=AttachmentOut,
    responses={200: {"model": AttachmentOut, "description": "The same file was already uploaded"}},
    **RAW_UPLOAD,
)
async def attachments_upload(
    product: str,
    request: Request,
    response: Response,
    filename: str = Query(min_length=1, max_length=1000),
    ctx: OrgContext = Depends(require_scope(WRITE_EXECUTION)),
    db: Session = Depends(get_db),
):
    """Uploads the raw request body as a file. The same content under the same name returns the row
    already there (200). No Idempotency-Key: the content itself makes a repeat safe."""
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    name = clean_filename(filename)
    mime = clean_mime(request.headers.get("content-type"))
    max_bytes = get_settings(request).attachment_max_bytes
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > max_bytes:
        raise HTTPException(413, f"The file is over {max_bytes} bytes")
    stored = await _store(request, ctx.org.id, request.stream(), max_bytes)
    return save(db, ctx, p.id, stored, name, mime, response)


@router.post(
    UPLOADS + "/base64",
    status_code=201,
    response_model=AttachmentOut,
    responses={200: {"model": AttachmentOut, "description": "The same file was already uploaded"}},
    **op("attachments_upload_base64", WRITE_EXECUTION, "execution"),
)
async def attachments_upload_base64(
    product: str,
    body: AttachmentBase64In,
    request: Request,
    response: Response,
    ctx: OrgContext = Depends(require_scope(WRITE_EXECUTION)),
    db: Session = Depends(get_db),
):
    """Uploads a small file (up to 5 MB) sent as base64 in JSON, for clients that can't send a raw body."""
    p = get_product(db, ctx, product)
    require_active_product(db, p.id)
    name, mime = clean_filename(body.filename), clean_mime(body.mime)
    try:
        data = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "content_base64 is not valid base64") from None
    max_bytes = min(BASE64_MAX_BYTES, get_settings(request).attachment_max_bytes)
    stored = await _store(request, ctx.org.id, one_chunk(data), max_bytes)
    return save(db, ctx, p.id, stored, name, mime, response)


@router.get(
    "/orgs/{org}/attachments/{id}",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/octet-stream": {}}}},
    **op("attachments_download", READ, "execution", mcp=False),
)
def attachments_download(
    id: str, request: Request, ctx: OrgContext = Depends(require_scope(READ)), db: Session = Depends(get_db)
):
    """The file's bytes, always as a download."""
    row = _get(db, ctx, Attachment, id, "Attachment")
    try:
        f = storage(request).open(row.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "The attachment's file is missing") from None

    def chunks():
        with f:
            while chunk := f.read(64 * 1024):
                yield chunk

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.filename, safe='')}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private",
        "Content-Length": str(row.size),
    }
    return StreamingResponse(chunks(), media_type=served_type(row.mime), headers=headers)
