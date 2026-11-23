"""Web adapter for Members, run in node against a live server: each load's state and mapped shape, the
server-side search, inviting (the one-time link), a new link, revoking, changing a role, removing, and raw
errors."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.web.live import LiveServer, as_sent, body_of, run_js

ORG = "/api/v1/orgs/acme"
URL = "/app?view=members"


@Suite(parameters=support.DATABASES)
class WebMembersAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def me(self):
        return self.live.owner.get("/api/v1/me").json()

    def invite(self, email, role):
        response = self.live.owner.post(f"{ORG}/invites", json={"email": email, "role": role})
        assert response.status_code == 201, response.text
        return response.json()

    def invites(self, status=None):
        query = f"?status={status}" if status else ""
        response = self.live.owner.get(f"{ORG}/invites{query}")
        assert response.status_code == 200, response.text
        return response.json()["items"]

    def js(self, body, email=None):
        sign_in = f"await h.signIn({json.dumps(email)});" if email else "await h.signIn();"
        return run_js(
            self.live,
            f"""{sign_in}
            const ctx = await h.ctx({{ view: "members" }});
            const m = await h.adapter("members");
            {body}""",
            URL,
        )

    def load(self, params, email=None):
        return self.js(f"return await m.load({json.dumps(params)}, ctx);", email)

    @test()
    def test_list_maps_members_roles_agents_and_last_active(self, suite_parameter):
        lee = support.add_member(self.live.owner, "lee@example.com", "editor")
        agent = self.live.owner.post(
            f"{ORG}/agents", json={"name": "ci-reporter", "role": "tester", "owner_user_id": lee["user_id"]}
        )
        assert agent.status_code == 201, agent.text
        out = self.load({})
        assert out["state"] == "list"
        d = out["data"]
        assert (d["total"], d["q"], d["pending"], d["pendingTotal"]) == (2, "", [], 0)
        rows = {m["email"]: m for m in d["members"]}
        owner = rows[support.OWNER_EMAIL]
        assert d["me"] == owner["handle"] and owner["userId"] == self.me()["user_id"]
        assert (owner["role"], owner["active"], owner["agents"]) == ("owner", "now", 0)
        assert rows["lee@example.com"] == {
            "handle": lee["actor_id"],
            "userId": lee["user_id"],
            "email": "lee@example.com",
            "role": "editor",
            "active": "",
            "agents": 1,
        }
        assert [r["role"] for r in d["roles"]] == ["owner", "admin", "editor", "tester", "viewer"]

    @test()
    def test_search_is_the_servers_q(self, suite_parameter):
        support.add_member(self.live.owner, "lee@example.com", "editor")
        support.add_member(self.live.owner, "sam@example.com", "tester")
        out = self.js(
            """const s = await m.load({ q: "lee" }, ctx);
            const asked = h.calls.map((c) => c.path).filter((p) => p.includes("/members?"));
            return { s, asked };"""
        )
        assert out["s"]["state"] == "search"
        assert [x["email"] for x in out["s"]["data"]["members"]] == ["lee@example.com"]
        assert out["s"]["data"]["total"] == 3
        assert "/api/v1/orgs/acme/members?q=lee&limit=200" in out["asked"]
        none = self.load({"q": "nobody"})
        assert none["state"] == "search-empty" and none["data"]["members"] == []

    @test()
    def test_pending_maps_open_invites(self, suite_parameter):
        made = self.invite("mira@example.com", "tester")
        out = self.load({"ui": "pending"})
        assert out["state"] == "pending" and out["data"]["pendingTotal"] == 1
        [p] = out["data"]["pending"]
        assert (p["id"], p["email"], p["role"], p["invitedBy"]) == (
            made["id"],
            "mira@example.com",
            "tester",
            made["invited_by_actor_id"],
        )
        assert (p["when"], p["expiresIn"]) == ("just now", 7)
        # the link is shown once: a reload of #invite-sent is the pending list
        assert self.load({"ui": "invite-sent"})["state"] == "pending"
        assert self.load({"ui": "invite"})["state"] == "invite"

    @test()
    def test_invite_creates_a_link_to_the_accept_view(self, suite_parameter):
        out = self.js(
            """const x = await m.actions.invite({ email: "mira@example.com", role: "tester" }, ctx);
            const sent = await m.load({}, ctx, { invite: x, app: "http://tcms.example.com/app" });
            const link = new URL(sent.data.sent.link);
            const params = Object.fromEntries(link.searchParams);
            const accept = await (await h.adapter("accept")).load(params, null);
            return { x, sent, view: link.searchParams.get("view"), token: accept.data.token };"""
        )
        assert out["sent"]["state"] == "invite-sent"
        assert out["sent"]["data"]["sent"]["email"] == "mira@example.com"
        assert out["sent"]["data"]["sent"]["role"] == "tester"
        assert out["view"] == "accept" and out["token"] == out["x"]["token"]
        assert out["x"]["token"].startswith("tji_")
        [row] = self.invites()
        assert (row["id"], row["email"], row["status"]) == (out["x"]["id"], "mira@example.com", "pending")
        assert out["sent"]["data"]["pending"][0]["id"] == row["id"]

    @test()
    def test_new_link_revokes_then_creates(self, suite_parameter):
        old = self.invite("mira@example.com", "viewer")
        out = self.js(
            """const p = (await m.load({ ui: "pending" }, ctx)).data.pending[0];
            return await m.actions.relink(p, ctx);"""
        )
        assert out["id"] != old["id"] and (out["email"], out["role"]) == ("mira@example.com", "viewer")
        assert [r["id"] for r in self.invites()] == [out["id"]]
        assert [r["id"] for r in self.invites("revoked")] == [old["id"]]

    @test()
    def test_revoke_removes_the_invite(self, suite_parameter):
        made = self.invite("mira@example.com", "tester")
        out = self.js(
            f"""await m.actions.revoke({json.dumps(made["id"])}, ctx);
            return await m.load({{ ui: "invite-revoked" }}, ctx);"""
        )
        assert out["state"] == "invite-revoked" and out["data"]["pending"] == []
        assert [r["id"] for r in self.invites("revoked")] == [made["id"]]

    @test()
    def test_change_role(self, suite_parameter):
        lee = support.add_member(self.live.owner, "lee@example.com", "editor")
        opened = self.load({"id": lee["actor_id"], "ui": "change-role"})
        assert opened["state"] == "change-role" and opened["data"]["open"] == lee["actor_id"]
        out = self.js(
            f"""const x = await m.actions.setRole({json.dumps(lee["user_id"])}, "tester", ctx);
            const after = await m.load({{ id: {json.dumps(lee["actor_id"])}, ui: "role-changed" }}, ctx);
            return {{ x, after }};"""
        )
        assert out["x"]["role"] == "tester"
        assert out["after"]["state"] == "role-changed"
        assert out["after"]["data"]["roleChange"] == {"handle": lee["actor_id"], "role": "tester"}
        back = {m["user_id"]: m["role"] for m in self.live.owner.get(f"{ORG}/members").json()["items"]}
        assert back[lee["user_id"]] == "tester"

    @test()
    def test_remove(self, suite_parameter):
        lee = support.add_member(self.live.owner, "lee@example.com", "editor")
        confirm = self.load({"id": lee["actor_id"], "ui": "remove-confirm"})
        assert confirm["state"] == "remove-confirm"
        assert confirm["data"]["remove"] == {"handle": lee["actor_id"]}
        out = self.js(
            f"""await m.actions.remove({json.dumps(lee["user_id"])}, ctx);
            const ctx2 = await h.ctx({{ view: "members" }});
            return await m.load({{ id: {json.dumps(lee["actor_id"])}, ui: "removed" }}, ctx2);"""
        )
        assert out["state"] == "removed" and out["data"]["removed"] == lee["actor_id"]
        assert out["data"]["total"] == 1
        assert [x["email"] for x in out["data"]["members"]] == [support.OWNER_EMAIL]
        emails = [m["email"] for m in self.live.owner.get(f"{ORG}/members").json()["items"]]
        assert "lee@example.com" not in emails

    @test()
    def test_invite_of_a_member_is_the_raw_409(self, suite_parameter):
        out = self.js(
            f"""const form = {{ email: {json.dumps(support.OWNER_EMAIL)}, role: "tester" }};
            const e = await h.fail(m.actions.invite(form, ctx));
            const shown = await m.load({{}}, ctx, {{ draft: form, raw: e.raw }});
            return {{ e, shown }};"""
        )
        again = {"email": support.OWNER_EMAIL, "role": "tester"}
        raw = as_sent(self.live.owner.post(f"{ORG}/invites", json=again))
        assert (body_of(raw)["status"], body_of(raw)["detail"]) == (409, "Already a member")
        assert out["e"] == {"name": "ApiError", "status": 409, "raw": raw}
        assert out["shown"]["state"] == "invite-error"
        assert out["shown"]["data"]["draft"] == {"email": support.OWNER_EMAIL, "role": "tester", "error": raw}

    @test()
    def test_a_member_without_admin_sees_members_only(self, suite_parameter):
        support.add_member(self.live.owner, "vic@example.com", "viewer")
        self.invite("mira@example.com", "tester")
        out = self.load({}, "vic@example.com")
        assert out["state"] == "list"
        assert out["data"]["pending"] == [] and out["data"]["pendingTotal"] == 0
        assert out["data"]["total"] == 2
