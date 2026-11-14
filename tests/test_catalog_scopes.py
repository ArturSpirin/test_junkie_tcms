"""Viewers read, editors plan, admins manage the catalog; limited tokens see only their products."""

import pytest
from catalog_seed import OPERATION_NAMES, call, make_product, ok, operations, seed, url
from conftest import add_member, bearer, login

WRITES = [o for o in OPERATION_NAMES if not o.endswith(("_list", "_get"))]


def _member(owner, client_factory, role):
    add_member(owner, f"{role}@example.com", role)
    client = client_factory()
    login(client, f"{role}@example.com")
    return client


@pytest.mark.parametrize("op_name", WRITES)
def test_viewer_reads_but_cant_write(owner, client_factory, op_name):
    s = seed(owner)
    viewer = _member(owner, client_factory, "viewer")
    assert call(viewer, op_name, s).status_code == 403
    for read in ("products_get", "features_list", "releases_get", "plans_get"):
        assert call(viewer, read, s).status_code == 200


@pytest.mark.parametrize("op_name", WRITES)
def test_editor_writes_plans_not_catalog(owner, client_factory, op_name):
    s = seed(owner)
    editor = _member(owner, client_factory, "editor")
    [scope] = [o[3] for o in operations(s) if o[0] == op_name]
    expected_ok = scope == "write:planning"
    status = call(editor, op_name, s).status_code
    assert (status < 300) == expected_ok, status
    if not expected_ok:
        assert status == 403


@pytest.fixture
def limited(owner, client_factory):
    """Two products; a token limited to the first."""
    a = seed(owner, "AAA")
    b = seed(owner, "BBB")
    token = ok(
        owner.post(
            url("/tokens"),
            json={
                "name": "a-only",
                "scopes": ["read", "write:catalog", "write:planning"],
                "product_ids": [a["product"]["id"]],
            },
        ),
        201,
    )["token"]
    return a, b, bearer(client_factory, token)


@pytest.mark.parametrize("op_name", OPERATION_NAMES)
def test_product_limited_token_gets_404_for_other_products(limited, op_name):
    a, b, api = limited
    if op_name == "products_list":
        assert [p["key"] for p in ok(api.get(url("/products")))["items"]] == ["AAA"]
        return
    response = call(api, op_name, b)
    assert response.status_code == 404, response.text
    assert call(api, op_name, a).status_code < 300


def test_product_limited_token_cant_create_products_or_link_hidden_features(limited):
    a, b, api = limited
    assert api.post(url("/products"), json={"key": "NEW", "name": "x"}).status_code == 403
    release = a["release"]["id"]
    assert (
        api.put(url(f"/releases/{release}/features"), json={"feature_ids": [b["child"]["id"]]}).status_code
        == 422
    )


def test_product_limited_token_reads_by_key_only_its_own(limited, owner):
    _, _, api = limited
    assert api.get(url("/products/AAA")).status_code == 200
    assert api.get(url("/products/BBB")).status_code == 404
    make_product(owner, "CCC")
    assert [p["key"] for p in ok(api.get(url("/products")))["items"]] == ["AAA"]
