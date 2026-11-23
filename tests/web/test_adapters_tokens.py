"""Web adapter for Tokens and agents, run in node against a live server: each load's state and mapped shape,
creating a token (the one-time secret), revoking it, creating, disabling and enabling an agent, the
own-tokens-only view without admin, and the raw 422."""

import json
from datetime import UTC, datetime, timedelta

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.web.live import LiveServer, as_sent, body_of, run_js

ORG = "/api/v1/orgs/acme"
URL = "/app?view=tokens"


@Suite(parameters=support.DATABASES)
class WebTokensAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def post(self, path, body, code=201):
        response = self.live.owner.post(f"{ORG}/{path}", json=body)
        assert response.status_code == code, response.text
        return response.json()

    def product(self):
        return self.post("products", {"key": "PAY", "name": "Payments"})

    def agent(self, name="ci-reporter", role="tester", **body):
        owner = self.live.owner.get("/api/v1/me").json()["user_id"]
        return self.post("agents", {"name": name, "role": role, "owner_user_id": owner, **body})

    def tokens(self):
        return {t["id"]: t for t in self.live.owner.get(f"{ORG}/tokens").json()["items"]}

    def js(self, body, email=None):
        sign_in = f"await h.signIn({json.dumps(email)});" if email else "await h.signIn();"
        return run_js(
            self.live,
            f"""{sign_in}
            const ctx = await h.ctx({{ view: "tokens" }});
            const t = await h.adapter("tokens");
            {body}""",
            URL,
        )

    def load(self, params, email=None):
        return self.js(f"return await t.load({json.dumps(params)}, ctx);", email)

    @test()
    def test_list_maps_tokens_and_agents(self, suite_parameter):
        pay = self.product()
        bot = self.agent(description="Posts results from CI")
        soon = (datetime.now(UTC) + timedelta(days=5)).isoformat()
        mine = self.post("tokens", {"name": "local scripts", "scopes": ["read", "audit:read"]})
        scopes = ["read", "write:execution"]
        ci = self.post(
            "tokens",
            {
                "name": "CI",
                "scopes": scopes,
                "actor_id": bot["id"],
                "product_ids": [pay["id"]],
                "expires_at": soon,
            },
        )
        out = self.load({})
        assert out["state"] == "tokens"
        d = out["data"]
        assert d["self"] is None
        rows = {r["id"]: r for r in d["tokens"]}
        [me] = self.live.owner.get(f"{ORG}/members").json()["items"]
        assert rows[mine["id"]]["owner"] == {"kind": "person", "handle": me["actor_id"]}
        assert rows[mine["id"]]["prefix"] == "tjt_" + mine["prefix"]
        assert (rows[mine["id"]]["expires"], rows[mine["id"]]["status"], rows[mine["id"]]["lastUsed"]) == (
            "never",
            "active",
            "never",
        )
        assert rows[mine["id"]]["products"] == [] and rows[mine["id"]]["scopes"] == ["audit:read", "read"]
        assert rows[ci["id"]]["owner"] == {"kind": "agent", "handle": "ci-reporter"}
        assert (rows[ci["id"]]["products"], rows[ci["id"]]["status"]) == (["PAY"], "expiring")
        [a] = d["agents"]
        assert (a["id"], a["name"], a["desc"], a["owner"], a["role"], a["tokens"], a["status"]) == (
            bot["id"],
            "ci-reporter",
            "Posts results from CI",
            me["actor_id"],
            "tester",
            1,
            "active",
        )
        assert [p["key"] for p in d["products"]] == ["PAY"]
        assert {o["userId"] for o in d["owners"]} == {me["user_id"]}
        assert self.load({"ui": "agents"})["state"] == "agents"
        assert self.load({"ui": "create-agent"})["state"] == "create-agent"
        made = self.load({"ui": "create", "owner": bot["id"]})
        assert made["state"] == "create" and made["data"]["draft"]["owner"] == bot["id"]

    @test()
    def test_create_shows_the_secret_once(self, suite_parameter):
        self.product()
        out = self.js(
            """const form = { name: "Nightly", owner: "me", scopes: ["read", "write:execution"],
              products: ["PAY"], expiry: "30" };
            const x = await t.actions.create(form, ctx);
            return { x, shown: await t.load({}, ctx, { token: x, origin: "http://tcms.example.com" }),
              again: await t.load({ ui: "created" }, ctx) };"""
        )
        x = out["x"]
        assert x["token"].startswith(f"tjt_{x['prefix']}_")
        assert out["shown"]["state"] == "created"
        c = out["shown"]["data"]["created"]
        assert (c["secret"], c["prefix"], c["products"]) == (x["token"], "tjt_" + x["prefix"], ["PAY"])
        assert out["shown"]["data"]["baseUrl"] == "http://tcms.example.com"
        # a reload can't show the secret again
        assert out["again"]["state"] == "tokens"
        back = self.tokens()[x["id"]]
        assert (back["name"], back["scopes"]) == ("Nightly", ["read", "write:execution"])
        left = datetime.fromisoformat(back["expires_at"].replace("Z", "+00:00")) - datetime.now(UTC)
        assert timedelta(days=29) < left <= timedelta(days=30)

    @test()
    def test_revoke(self, suite_parameter):
        tok = self.post("tokens", {"name": "old jenkins", "scopes": ["read"]})
        confirm = self.load({"id": tok["id"], "ui": "revoke-confirm"})
        assert confirm["state"] == "revoke-confirm" and confirm["data"]["revoke"] == tok["id"]
        out = self.js(
            f"""await t.actions.revoke({json.dumps(tok["id"])}, ctx);
            return await t.load({{ ui: "revoked" }}, ctx);"""
        )
        assert out["state"] == "revoked"
        [row] = out["data"]["tokens"]
        assert (row["status"], row["expires"]) == ("revoked", "–")
        assert self.tokens()[tok["id"]]["revoked_at"] is not None
        # a revoked token has no confirm step
        assert self.load({"id": tok["id"], "ui": "revoke-confirm"})["state"] == "tokens"

    @test()
    def test_create_disable_and_enable_an_agent(self, suite_parameter):
        out = self.js(
            """const owner = (await t.load({}, ctx)).data.owners[0];
            const a = await t.actions.createAgent({ name: "triage-bot", ownerUserId: owner.userId,
              desc: "Drafts case edits", role: "editor" }, ctx);
            const off = await t.actions.disable(a.id, ctx);
            const shown = await t.load({ id: a.id, ui: "agent-disabled" }, ctx);
            const on = await t.actions.enable(a.id, ctx);
            const after = await t.load({ id: a.id, ui: "agent-disabled" }, ctx);
            return { a, off, shown, on, after };"""
        )
        a = out["a"]
        assert (a["name"], a["role"], a["description"]) == ("triage-bot", "editor", "Drafts case edits")
        assert out["off"]["disabled_at"] is not None
        assert out["shown"]["state"] == "agent-disabled" and out["shown"]["data"]["disabled"] == a["id"]
        assert out["shown"]["data"]["agents"][0]["status"] == "disabled"
        assert out["on"]["disabled_at"] is None
        assert out["after"]["state"] == "agents" and out["after"]["data"]["agents"][0]["status"] == "active"
        [back] = self.live.owner.get(f"{ORG}/agents").json()["items"]
        assert back["disabled_at"] is None and back["description"] == "Drafts case edits"

    @test()
    def test_without_admin_only_own_tokens(self, suite_parameter):
        lee = support.add_member(self.live.owner, "lee@example.com", "tester")
        self.post("tokens", {"name": "owner's", "scopes": ["read"]})
        out = self.js(
            """const x = await t.actions.create({ name: "laptop", owner: "me", scopes: ["read"], products: [],
              expiry: "never" }, ctx);
            return { x, view: await t.load({}, ctx) };""",
            "lee@example.com",
        )
        assert out["view"]["state"] == "self-only"
        d = out["view"]["data"]
        assert d["self"] == lee["actor_id"] and d["agents"] == []
        assert [r["name"] for r in d["tokens"]] == ["laptop"]
        assert self.tokens()[out["x"]["id"]]["actor_id"] == lee["actor_id"]

    @test()
    def test_scope_above_the_owners_role_is_the_raw_422(self, suite_parameter):
        bot = self.agent()
        form = {"name": "CI", "owner": bot["id"], "scopes": ["read", "admin"], "products": [], "expiry": "90"}
        out = self.js(
            f"""const form = {json.dumps(form)};
            const e = await h.fail(t.actions.create(form, ctx));
            return {{ e, shown: await t.load({{}}, ctx, {{ form, raw: e.raw }}) }};"""
        )
        raw = as_sent(
            self.live.owner.post(
                f"{ORG}/tokens", json={"name": "CI", "scopes": ["read", "admin"], "actor_id": bot["id"]}
            )
        )
        assert body_of(raw)["status"] == 422
        assert out["e"] == {"name": "ApiError", "status": 422, "raw": raw}
        assert out["shown"]["state"] == "error-422"
        e = out["shown"]["data"]["error"]
        assert (e["owner"], e["ownerRole"], e["bad"], e["raw"]) == ("ci-reporter", "tester", "admin", raw)
