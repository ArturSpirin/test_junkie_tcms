"""Viewers read, editors plan, admins manage the catalog; limited tokens see only their products."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import OPERATION_NAMES, call, make_product, ok, operations, seed, url
from tests.support import add_member, login

WRITES = [o for o in OPERATION_NAMES if not o.endswith(("_list", "_get"))]


def _member(owner, env, role):
    add_member(owner, f"{role}@example.com", role)
    client = env.client()
    login(client, f"{role}@example.com")
    return client


@Suite(parameters=support.DATABASES)
class CatalogScopes:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def limited(self):
        """Two products; a token limited to the first."""
        owner = self.env.owner
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
        return a, b, self.env.bearer(token)

    @test(parameters=WRITES)
    def test_viewer_reads_but_cant_write(self, parameter, suite_parameter):
        op_name = parameter
        owner = self.env.owner
        s = seed(owner)
        viewer = _member(owner, self.env, "viewer")
        assert call(viewer, op_name, s).status_code == 403
        for read in ("products_get", "features_list", "releases_get", "plans_get"):
            assert call(viewer, read, s).status_code == 200

    @test(parameters=WRITES)
    def test_editor_writes_plans_not_catalog(self, parameter, suite_parameter):
        op_name = parameter
        owner = self.env.owner
        s = seed(owner)
        editor = _member(owner, self.env, "editor")
        [scope] = [o[3] for o in operations(s) if o[0] == op_name]
        expected_ok = scope == "write:planning"
        status = call(editor, op_name, s).status_code
        assert (status < 300) == expected_ok, status
        if not expected_ok:
            assert status == 403

    @test(parameters=OPERATION_NAMES)
    def test_product_limited_token_gets_404_for_other_products(self, parameter, suite_parameter):
        op_name = parameter
        a, b, api = self.limited()
        if op_name == "products_list":
            assert [p["key"] for p in ok(api.get(url("/products")))["items"]] == ["AAA"]
            return
        response = call(api, op_name, b)
        assert response.status_code == 404, response.text
        assert call(api, op_name, a).status_code < 300

    @test()
    def test_product_limited_token_cant_create_products_or_link_hidden_features(self, suite_parameter):
        a, b, api = self.limited()
        assert api.post(url("/products"), json={"key": "NEW", "name": "x"}).status_code == 403
        release = a["release"]["id"]
        assert (
            api.put(
                url(f"/releases/{release}/features"), json={"feature_ids": [b["child"]["id"]]}
            ).status_code
            == 422
        )

    @test()
    def test_product_limited_token_reads_by_key_only_its_own(self, suite_parameter):
        _, _, api = self.limited()
        owner = self.env.owner
        assert api.get(url("/products/AAA")).status_code == 200
        assert api.get(url("/products/BBB")).status_code == 404
        make_product(owner, "CCC")
        assert [p["key"] for p in ok(api.get(url("/products")))["items"]] == ["AAA"]
