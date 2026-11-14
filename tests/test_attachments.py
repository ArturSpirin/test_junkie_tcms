"""Attachments: raw and base64 uploads, content dedupe, the org-scoped store, safe downloads (T4)."""

import base64
from pathlib import Path

from catalog_seed import events, make_product, ok, url
from conftest import login
from test_junkie_tcms.api.v1 import attachments


def upload(client, product: str, content: bytes, name: str = "shot.png", mime: str = "image/png", org: str = "acme"):
    return client.post(
        url(f"/products/{product}/attachments", org),
        params={"filename": name},
        content=content,
        headers={"Content-Type": mime},
    )


def stored_files(settings, sha: str) -> list[Path]:
    return list(Path(settings.attachments_dir).glob(f"*/{sha[:2]}/{sha}"))


def test_upload_then_download_the_same_bytes(owner, settings):
    p = make_product(owner)["id"]
    row = ok(upload(owner, p, b"\x89PNG one"), 201)
    assert (row["filename"], row["mime"], row["size"], row["product_id"]) == ("shot.png", "image/png", 8, p)
    assert len(stored_files(settings, row["sha256"])) == 1

    download = owner.get(url(f"/attachments/{row['id']}"))
    assert download.status_code == 200
    assert download.content == b"\x89PNG one"
    assert download.headers["content-type"] == "image/png"
    assert download.headers["content-disposition"] == "attachment; filename*=UTF-8''shot.png"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["cache-control"] == "private"
    [event] = events(owner, "attachment")
    assert event["action"] == "attachment.upload"


def test_the_same_content_and_name_returns_the_row_already_there(owner, settings):
    p = make_product(owner)["id"]
    first = ok(upload(owner, p, b"same"), 201)
    again = ok(upload(owner, p, b"same"), 200)
    assert again["id"] == first["id"]
    renamed = ok(upload(owner, p, b"same", "other.png"), 201)
    assert renamed["id"] != first["id"] and renamed["sha256"] == first["sha256"]
    assert len(stored_files(settings, first["sha256"])) == 1  # one file for both names
    assert len(events(owner, "attachment")) == 2


def test_a_racing_duplicate_upload_returns_200_not_500(owner, monkeypatch):
    p = make_product(owner)["id"]
    first = ok(upload(owner, p, b"race"), 201)
    real = attachments.find_existing
    calls = []

    def miss_once(*args):
        calls.append(args)
        return None if len(calls) == 1 else real(*args)

    # The lookup misses as if the other upload had not committed yet, so the insert hits the unique key.
    monkeypatch.setattr(attachments, "find_existing", miss_once)
    raced = ok(upload(owner, p, b"race"), 200)
    assert raced["id"] == first["id"]
    assert len(calls) == 2
    assert len(events(owner, "attachment")) == 1


def test_two_orgs_uploading_the_same_file_get_two_stored_files(owner, client_factory, settings):
    p = make_product(owner)["id"]
    gus = client_factory()
    login(gus, "other@example.com")
    q = make_product(gus, org="globex")["id"]
    a = ok(upload(owner, p, b"shared bytes"), 201)
    b = ok(upload(gus, q, b"shared bytes", org="globex"), 201)
    assert a["sha256"] == b["sha256"]
    assert len(stored_files(settings, a["sha256"])) == 2


def test_an_upload_over_the_cap_is_413(owner, app, monkeypatch):
    p = make_product(owner)["id"]
    small = app.state.settings.model_copy(update={"attachment_max_bytes": 10})
    monkeypatch.setattr(app.state, "settings", small)
    assert upload(owner, p, b"x" * 11).status_code == 413
    ok(upload(owner, p, b"x" * 10), 201)
    big = base64.b64encode(b"y" * 11).decode()
    body = {"filename": "big.bin", "content_base64": big}
    assert owner.post(url(f"/products/{p}/attachments/base64"), json=body).status_code == 413


def test_base64_upload_and_bad_base64(owner):
    p = make_product(owner)["id"]
    body = {"filename": "note.txt", "mime": "text/plain", "content_base64": base64.b64encode(b"hello").decode()}
    row = ok(owner.post(url(f"/products/{p}/attachments/base64"), json=body), 201)
    assert (row["size"], row["mime"]) == (5, "text/plain")
    assert owner.get(url(f"/attachments/{row['id']}")).content == b"hello"
    bad = owner.post(url(f"/products/{p}/attachments/base64"), json={"filename": "x", "content_base64": "%%%"})
    assert bad.status_code == 422


def test_html_and_svg_download_as_octet_stream_with_a_safe_name(owner):
    p = make_product(owner)["id"]
    page = ok(upload(owner, p, b"<script>alert(1)</script>", "x.html", "text/html"), 201)
    svg = ok(upload(owner, p, b"<svg/>", "y.svg", "image/svg+xml"), 201)
    for row in (page, svg):
        download = owner.get(url(f"/attachments/{row['id']}"))
        assert download.headers["content-type"] == "application/octet-stream"
        assert download.headers["content-disposition"].startswith("attachment;")
    odd = ok(upload(owner, p, b"z", "../a bé.png"), 201)
    assert "/" not in odd["filename"] and "\\" not in odd["filename"]
