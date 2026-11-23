"""Web adapters for the shell context, Products and Versions, run in node against a live server: each load's
state and mapped shape, the server-side name search, the writes, and raw errors."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.web.live import LiveServer, as_sent, body_of, run_js

ORG = "/api/v1/orgs/acme"


@Suite(parameters=support.DATABASES)
class WebCatalogAdapters:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def seed(self, *products):
        """Create (key, name, description) products through the API; returns their ProductOut."""
        made = []
        for key, name, desc in products:
            response = self.live.owner.post(
                f"{ORG}/products", json={"key": key, "name": name, "description": {"markdown": desc}}
            )
            assert response.status_code == 201, response.text
            made.append(response.json())
        return made

    def release(self, product, version, **body):
        response = self.live.owner.post(
            f"{ORG}/products/{product}/releases", json={"version": version, "name": version, **body}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def load(self, view, params, url=None):
        """The adapter's { state, data } for params, signed in as the acme owner, with the shell's context."""
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps(params)};
            const ctx = await h.ctx(params);
            return await (await h.adapter("{view}")).load(params, ctx);""",
            url or f"/app?view={view}",
        )

    @test()
    def test_context_is_the_signed_in_org_its_products_and_people(self, suite_parameter):
        self.seed(("PAY", "Payments", "Card payments"), ("ID", "Identity", "Sign-in"))
        self.release("PAY", "2.14.0", status="in_progress")
        ctx = run_js(self.live, "await h.signIn(); return await h.ctx({ view: 'products' });")
        assert ctx["org"] == {"id": "acme", "name": "Acme"}
        assert [o["id"] for o in ctx["orgs"]] == ["acme"] and ctx["orgs"][0]["products"] == 2
        assert ctx["user"]["role"] == "owner"
        assert ctx["people"][ctx["user"]["handle"]][0] == "Olive Owner"
        assert sorted(p["key"] for p in ctx["products"]) == ["ID", "PAY"]
        assert ctx["nav"]["products"] == 2
        assert ctx["product"]["key"] in ("ID", "PAY")

    @test()
    def test_context_takes_the_product_from_the_url(self, suite_parameter):
        self.seed(("PAY", "Payments", ""), ("ID", "Identity", ""))
        self.release("PAY", "2.14.0", status="in_progress")
        ctx = run_js(self.live, "await h.signIn(); return await h.ctx({ product: 'PAY' });")
        assert ctx["product"]["key"] == "PAY"
        assert ctx["version"]["ver"] == "2.14.0" and ctx["version"]["status"] == "in progress"
        assert [v["ver"] for v in ctx["versions"]] == ["2.14.0"]

    @test()
    def test_no_products_is_the_empty_state(self, suite_parameter):
        out = self.load("products", {})
        assert out["state"] == "empty"
        assert out["data"]["products"] == [] and out["data"]["total"] == 0
        assert self.load("products", {"ui": "new"})["state"] == "new-first"

    @test()
    def test_list_maps_each_product_to_its_card(self, suite_parameter):
        self.seed(("PAY", "Payments", "Card payments"), ("ID", "Identity", "Sign-in"))
        self.release("PAY", "2.14.0", status="in_progress")
        out = self.load("products", {})
        assert out["state"] == "list" and out["data"]["total"] == 2
        cards = {p["key"]: p for p in out["data"]["products"]}
        assert cards["PAY"]["desc"] == "Card payments"
        assert (cards["PAY"]["versions"], cards["PAY"]["latest"]) == (1, "2.14.0 in progress")
        assert (cards["ID"]["versions"], cards["ID"]["features"], cards["ID"]["cases"]) == (0, 0, 0)
        assert self.load("products", {"ui": "new"})["state"] == "new"

    @test()
    def test_search_is_the_servers_q(self, suite_parameter):
        self.seed(("PAY", "Payments", ""), ("ID", "Identity", ""), ("WEB", "Storefront", ""))
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx();
            const s = await (await h.adapter("products")).load({ q: "pay" }, ctx);
            const asked = h.calls.map((c) => c.path).filter((p) => p.includes("/products?"));
            return { s, asked };""",
        )
        assert out["s"]["state"] == "search"
        assert [p["key"] for p in out["s"]["data"]["products"]] == ["PAY"]
        assert out["s"]["data"]["total"] == 3
        assert "/api/v1/orgs/acme/products?q=pay&limit=200" in out["asked"]
        none = self.load("products", {"q": "billing"})
        assert none["state"] == "search-empty" and none["data"]["products"] == []

    @test()
    def test_create_makes_the_product_and_its_first_version(self, suite_parameter):
        self.seed(("PAY", "Payments", ""))
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx();
            const products = await h.adapter("products");
            const form = { key: "KYC", name: "Partner onboarding", desc: "Identity checks", copyFrom: "PAY",
              firstVersion: true };
            const p = await products.actions.create(form, ctx);
            return { p, after: await products.load({ created: "KYC" }, ctx) };""",
        )
        assert (out["p"]["key"], out["p"]["description"]) == ("KYC", "Identity checks")
        assert out["after"]["state"] == "created"
        assert out["after"]["data"]["created"]["key"] == "KYC"
        assert out["after"]["data"]["created"]["latest"] == "1.0.0 planned"
        assert [p["key"] for p in out["after"]["data"]["products"]] == ["PAY"]

    @test()
    def test_duplicate_key_is_the_raw_409(self, suite_parameter):
        self.seed(("PAY", "Payments", ""))
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx();
            const products = await h.adapter("products");
            const form = { key: "PAY", name: "Again", desc: "", copyFrom: "none", firstVersion: false };
            return h.fail(products.actions.create(form, ctx));""",
        )
        raw = as_sent(self.live.owner.post(f"{ORG}/products", json={"key": "PAY", "name": "Again"}))
        assert body_of(raw)["status"] == 409
        assert out == {"name": "ApiError", "status": 409, "raw": raw}

    @test()
    def test_detail_maps_versions_features_and_kpis(self, suite_parameter):
        [pay] = self.seed(("PAY", "Payments", "Card payments"))
        feature = self.live.owner.post(f"{ORG}/products/PAY/features", json={"name": "Checkout"})
        assert feature.status_code == 201, feature.text
        rel = self.release("PAY", "2.14.0", status="in_progress")
        put = self.live.owner.put(
            f"{ORG}/releases/{rel['id']}/features", json={"feature_ids": [feature.json()["id"]]}
        )
        assert put.status_code == 200, put.text
        self.release("PAY", "2.15.0")
        out = self.load("products", {"id": "PAY", "view": "products"})
        assert out["state"] == "detail"
        d = out["data"]["detail"]
        assert (d["key"], d["name"], d["desc"]) == ("PAY", "Payments", "Card payments")
        assert (d["kpis"]["versions"], d["kpis"]["inProgress"], d["kpis"]["planned"]) == (2, 1, 1)
        assert (d["kpis"]["features"], d["kpis"]["topLevel"]) == (1, 1)
        assert {v["ver"]: v["features"] for v in d["versions"]} == {"2.14.0": 1, "2.15.0": 0}
        assert d["features"] == [
            {"id": feature.json()["id"], "path": "Checkout", "cases": 0, "changedIn": "2.14.0"}
        ]
        assert pay["id"] == d["id"]

    @test()
    def test_unknown_product_is_the_raw_404(self, suite_parameter):
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx();
            return h.fail((await h.adapter("products")).load({ id: "NOPE" }, ctx));""",
        )
        assert out["status"] == 404
        assert out["raw"] == as_sent(self.live.owner.get(f"{ORG}/products/NOPE"))

    @test()
    def test_versions_list_and_empty(self, suite_parameter):
        self.seed(("PAY", "Payments", ""))
        empty = self.load("releases", {"product": "PAY"})
        assert empty["state"] == "empty" and empty["data"]["noVersionsFor"] == "PAY"
        # midday UTC, so the browser's local date is Oct 30 in any zone from UTC-11 to UTC+11
        self.release("PAY", "2.13.0", status="released", released_at="2026-10-30T12:00:00Z")
        self.release("PAY", "2.14.0", status="in_progress", target_date="2026-11-27")
        out = self.load("releases", {"product": "PAY"})
        assert out["state"] == "list"
        rows = {r["ver"]: r for r in out["data"]["versions"]}
        assert (rows["2.14.0"]["status"], rows["2.14.0"]["when"]) == ("in_progress", "Target Nov 27")
        assert rows["2.13.0"]["when"] == "Released Oct 30"
        assert out["data"]["product"]["key"] == "PAY"
        assert sorted(out["data"]["draft"]["copyable"]) == ["2.13.0", "2.14.0"]
        assert self.load("releases", {"product": "PAY", "ui": "new"})["state"] == "new"

    @test()
    def test_versions_create_update_and_set_features(self, suite_parameter):
        self.seed(("PAY", "Payments", ""))
        feature = self.live.owner.post(f"{ORG}/products/PAY/features", json={"name": "Checkout"}).json()
        first = self.release("PAY", "2.14.0")
        assert (
            self.live.owner.put(
                f"{ORG}/releases/{first['id']}/features", json={"feature_ids": [feature["id"]]}
            ).status_code
            == 200
        )
        out = run_js(
            self.live,
            f"""await h.signIn();
            const ctx = await h.ctx({{ product: "PAY" }});
            const rel = await h.adapter("releases");
            const form = {{ ver: "2.15.0", name: "Spring wallets", status: "planned", target: "2027-01-22",
              copyFrom: "2.14.0", notes: "Wallet limits" }};
            const made = await rel.actions.create(form, ctx, "PAY");
            const updated = await rel.actions.update(made.id, {{ status: "in_progress" }}, ctx);
            const cleared = await rel.actions.setFeatures("{first["id"]}", [], ctx);
            const detail = await rel.load({{ id: made.id, ui: "features-saved" }}, ctx);
            return {{ made, updated, cleared, detail }};""",
            "/app?view=releases&product=PAY",
        )
        assert (out["made"]["version"], out["made"]["target_date"], out["made"]["feature_ids"]) == (
            "2.15.0",
            "2027-01-22",
            [feature["id"]],
        )
        assert out["updated"]["status"] == "in_progress"
        assert out["cleared"]["feature_ids"] == []
        assert out["detail"]["state"] == "features-saved"
        d = out["detail"]["data"]["detail"]
        assert (d["ver"], d["status"], d["features"], d["notes"]) == (
            "2.15.0",
            "in_progress",
            1,
            "Wallet limits",
        )
        assert d["tree"] == [
            {"id": feature["id"], "path": "Checkout", "cases": 0, "inVersion": True, "sub": False}
        ]
        assert set(d["kpis"]) == {
            "inScope",
            "fromFeatures",
            "executedPct",
            "executed",
            "cycleCases",
            "passPct",
        }

    @test()
    def test_versions_create_error_is_raw(self, suite_parameter):
        self.seed(("PAY", "Payments", ""))
        self.release("PAY", "2.14.0")
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx({ product: "PAY" });
            const rel = await h.adapter("releases");
            const form = { ver: "2.14.0", name: "Again", status: "planned", target: "none", copyFrom: "none",
              notes: "" };
            return h.fail(rel.actions.create(form, ctx, "PAY"));""",
        )
        raw = as_sent(
            self.live.owner.post(f"{ORG}/products/PAY/releases", json={"version": "2.14.0", "name": "Again"})
        )
        assert out["status"] == body_of(raw)["status"] and out["status"] >= 400
        assert out["raw"] == raw
