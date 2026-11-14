"""One org can't read or write another org's catalog, through the API or straight into the database."""

import pytest
from catalog_seed import OPERATION_NAMES, call, ok, seed, url
from conftest import login
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_junkie_tcms.db.models import Org, ReleaseFeature


@pytest.fixture
def globex(client_factory):
    client = client_factory()
    login(client, "other@example.com")
    return client


@pytest.mark.parametrize("op_name", OPERATION_NAMES)
def test_other_org_gets_404_on_every_operation(owner, globex, op_name):
    s = seed(owner)
    if op_name == "products_list":
        ok(owner.get(url("/products")))
        assert ok(globex.get(url("/products", "globex")))["items"] == []
    else:
        response = call(globex, op_name, s, org="globex")
        assert response.status_code == 404, response.text
    assert call(globex, op_name, s, org="acme").status_code == 404
    after = ok(owner.get(url(f"/products/{s['product']['id']}")))
    assert (after["name"], after["archived_at"]) == (s["product"]["name"], None)


def test_other_org_ids_cant_be_linked(owner, globex):
    s = seed(owner)
    theirs = seed(globex, org="globex")
    their_release = theirs["release"]["id"]
    put = globex.put(
        url(f"/releases/{their_release}/features", "globex"), json={"feature_ids": [s["child"]["id"]]}
    )
    assert put.status_code == 422
    entries = {"entries": [{"feature_id": s["child"]["id"]}]}
    assert (
        globex.post(url(f"/plans/{theirs['plan']['id']}/entries", "globex"), json=entries).status_code == 422
    )
    body = {"name": "x", "parent_id": s["parent"]["id"]}
    assert (
        globex.post(url(f"/products/{theirs['product']['id']}/features", "globex"), json=body).status_code
        == 422
    )
    body = {"name": "x", "release_id": s["release"]["id"]}
    assert (
        globex.post(url(f"/products/{theirs['product']['id']}/plans", "globex"), json=body).status_code == 422
    )


def test_composite_foreign_key_refuses_a_cross_org_row(owner, globex, app):
    s = seed(owner)
    theirs = seed(globex, org="globex")
    with Session(app.state.engine) as db:
        globex_id = db.query(Org.id).filter(Org.slug == "globex").scalar()
        db.add(
            ReleaseFeature(org_id=globex_id, release_id=theirs["release"]["id"], feature_id=s["parent"]["id"])
        )
        with pytest.raises(IntegrityError):
            db.commit()
