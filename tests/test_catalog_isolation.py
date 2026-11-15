"""One org can't read or write another org's catalog, through the API or straight into the database."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.models import Org, ReleaseFeature
from tests import support
from tests.catalog_seed import OPERATION_NAMES, call, ok, seed, url
from tests.support import login


@Suite(parameters=support.DATABASES)
class CatalogIsolation:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def globex(self):
        client = self.env.client()
        login(client, "other@example.com")
        return client

    @test(parameters=OPERATION_NAMES)
    def test_other_org_gets_404_on_every_operation(self, parameter, suite_parameter):
        op_name = parameter
        owner = self.env.owner
        globex = self.globex()
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

    @test()
    def test_other_org_ids_cant_be_linked(self, suite_parameter):
        owner = self.env.owner
        globex = self.globex()
        s = seed(owner)
        theirs = seed(globex, org="globex")
        their_release = theirs["release"]["id"]
        put = globex.put(
            url(f"/releases/{their_release}/features", "globex"), json={"feature_ids": [s["child"]["id"]]}
        )
        assert put.status_code == 422
        entries = {"entries": [{"feature_id": s["child"]["id"]}]}
        assert (
            globex.post(url(f"/plans/{theirs['plan']['id']}/entries", "globex"), json=entries).status_code
            == 422
        )
        body = {"name": "x", "parent_id": s["parent"]["id"]}
        assert (
            globex.post(url(f"/products/{theirs['product']['id']}/features", "globex"), json=body).status_code
            == 422
        )
        body = {"name": "x", "release_id": s["release"]["id"]}
        assert (
            globex.post(url(f"/products/{theirs['product']['id']}/plans", "globex"), json=body).status_code
            == 422
        )

    @test()
    def test_composite_foreign_key_refuses_a_cross_org_row(self, suite_parameter):
        owner = self.env.owner
        globex = self.globex()
        app = self.env.app
        s = seed(owner)
        theirs = seed(globex, org="globex")
        with Session(app.state.engine) as db:
            globex_id = db.query(Org.id).filter(Org.slug == "globex").scalar()
            db.add(
                ReleaseFeature(
                    org_id=globex_id, release_id=theirs["release"]["id"], feature_id=s["parent"]["id"]
                )
            )
            with support.raises(IntegrityError):
                db.commit()
