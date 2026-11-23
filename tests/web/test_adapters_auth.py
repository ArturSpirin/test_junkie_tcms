"""Web adapters for sign-in and invite accept, run in node against a live server: api.js's cookies, CSRF
header, raw errors and 401 redirect, the signin adapter and the accept adapter's states."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.models import Invite
from tests import support
from tests.web.live import LiveServer, as_sent, body_of, run_js

LOGIN = "/api/v1/auth/login"
ACCEPT = "/api/v1/invites:accept"
INVITES = "/api/v1/orgs/acme/invites"
ME_401 = (
    'const e = await h.fail(h.api.get("/api/v1/me")); return { status: e.status, to: h.location.assigned };'
)


@Suite(parameters=support.DATABASES)
class WebAuthAdapters:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def invite(self, email):
        response = self.live.owner.post(INVITES, json={"email": email, "role": "tester"})
        assert response.status_code == 201, response.text
        return response.json()

    def server_says(self, path, body):
        """What the server answers a signed-out call with, as sent (status line, Content-Type, body)."""
        return as_sent(self.live.env.client().post(path, json=body))

    @test()
    def test_sign_in_sets_the_session_and_says_who(self, suite_parameter):
        out = run_js(
            self.live,
            "const me = await h.signIn(); return { me, cookies: Object.keys(h.cookies).sort() };",
            "/app?view=signin",
        )
        assert out["me"]["email"] == support.OWNER_EMAIL
        assert [o["slug"] for o in out["me"]["orgs"]] == ["acme"]
        assert out["cookies"] == ["tj_csrf", "tj_session"]

    @test()
    def test_wrong_password_is_the_raw_401(self, suite_parameter):
        out = run_js(
            self.live,
            """const signin = await h.adapter("signin");
            try { await h.signIn("owner@example.com", "wrong password"); } catch (e) {
              return { e: { name: e.name, status: e.status, raw: e.raw }, shown: signin.failure(e),
                assigned: h.location.assigned };
            }""",
            "/app?view=signin",
        )
        raw = self.server_says(LOGIN, {"email": support.OWNER_EMAIL, "password": "wrong password"})
        assert raw.startswith("HTTP/1.1 401 Unauthorized\nContent-Type: application/problem+json\n\n")
        assert body_of(raw)["detail"] == "Wrong email or password"
        assert out["e"] == {"name": "ApiError", "status": 401, "raw": raw}
        assert out["shown"] == {"state": "wrong", "raw": raw}
        assert out["assigned"] is None, "a 401 on the sign-in view must not redirect to sign-in"

    @test()
    def test_a_401_sends_the_page_to_sign_in_with_next(self, suite_parameter):
        out = run_js(
            self.live,
            ME_401,
            "/app?view=releases&id=r1#set-features",
        )
        assert out == {
            "status": 401,
            "to": "?view=signin&next=%2Fapp%3Fview%3Dreleases%26id%3Dr1%23set-features",
        }

    @test()
    def test_a_signed_out_page_load_stops_quietly_on_its_way_to_sign_in(self, suite_parameter):
        # main.js waits out the redirect: no uncaught 401 on the console of every signed-out load
        out = run_js(
            self.live,
            """const boot = h.boot().then(
                () => "loaded", (e) => `threw ${e.status ?? ""} ${e.message.split("\\n")[0]}`);
              const wait = new Promise((done) => setTimeout(() => done("waiting"), 1000));
              return { boot: await Promise.race([boot, wait]), to: h.location.assigned };""",
            "/app?view=cycles",
        )
        assert out == {"boot": "waiting", "to": "?view=signin&next=%2Fapp%3Fview%3Dcycles"}

    @test(parameters=["signin", "accept"])
    def test_a_401_on_the_auth_views_does_not_redirect(self, parameter, suite_parameter):
        out = run_js(
            self.live,
            ME_401,
            f"/app?view={parameter}",
        )
        assert out == {"status": 401, "to": None}

    @test()
    def test_every_write_sends_the_csrf_cookie_as_its_header(self, suite_parameter):
        out = run_js(
            self.live,
            """await h.signIn();
            const ctx = await h.ctx();
            const form = { key: "PAY", name: "Payments", desc: "", copyFrom: "none", firstVersion: true };
            await (await h.adapter("products")).actions.create(form, ctx);
            const writes = h.calls.filter((c) => c.method !== "GET" && c.path !== "/api/v1/auth/login");
            const sent = writes.map((c) => [c.method, c.path, c.headers["X-CSRF-Token"], c.credentials]);
            return { csrf: h.cookies.tj_csrf, sent };""",
        )
        assert out["csrf"]
        assert out["sent"] == [
            ["POST", "/api/v1/orgs/acme/products", out["csrf"], "same-origin"],
            ["POST", "/api/v1/orgs/acme/products/PAY/releases", out["csrf"], "same-origin"],
        ]

    @test()
    def test_sign_in_next_keeps_only_same_origin_paths(self, suite_parameter):
        out = run_js(
            self.live,
            """const s = await h.adapter("signin");
            const nexts = ["/app?view=releases", "?view=accept&token=t", "//example.com/x", "https://example.com"];
            return Promise.all(nexts.map(async (next) => (await s.load({ next })).data.next));""",
            "/app?view=signin",
        )
        assert out == ["/app?view=releases", "?view=accept&token=t", "", ""]

    @test()
    def test_sign_in_from_an_invite_shows_the_invite_state(self, suite_parameter):
        out = run_js(
            self.live,
            'return (await (await h.adapter("signin")).load({ next: "?view=accept&token=t" })).state;',
            "/app?view=signin",
        )
        assert out == "invite"

    @test()
    def test_signed_out_accept_makes_the_account_and_signs_it_in(self, suite_parameter):
        token = self.invite("nia@example.com")["token"]
        out = run_js(
            self.live,
            f"""const a = await h.adapter("accept");
            const first = await a.load({{ token: "{token}" }});
            const signup = {{ name: "Nia New", password: "correct horse" }};
            const member = await a.actions.accept("{token}", signup);
            const me = await h.api.get("/api/v1/me");
            const sent = h.calls.find((c) => c.path === "{ACCEPT}").body;
            return {{ state: first.state, member, me, sent }};""",
            f"/app?view=accept&token={token}",
        )
        assert out["state"] == "valid"
        assert (out["member"]["email"], out["member"]["role"]) == ("nia@example.com", "tester")
        assert (out["me"]["email"], out["me"]["name"]) == ("nia@example.com", "Nia New")
        assert out["sent"] == {"token": token, "name": "Nia New", "password": "correct horse"}

    @test()
    def test_signed_in_accept_sends_only_the_token(self, suite_parameter):
        token = self.invite("other@example.com")["token"]
        out = run_js(
            self.live,
            f"""await h.signIn("other@example.com");
            const a = await h.adapter("accept");
            const first = await a.load({{ token: "{token}" }});
            const member = await a.actions.accept(first.data.token, null);
            const me = await h.api.get("/api/v1/me");
            return {{ state: first.state, signedIn: first.data.signedIn, who: first.data.me.email, member,
              orgs: me.orgs.map((o) => o.slug).sort(),
              sent: h.calls.find((c) => c.path === "{ACCEPT}").body }};""",
            f"/app?view=accept&token={token}",
        )
        assert (out["state"], out["signedIn"]) == ("signedin", True)
        assert out["who"] == "other@example.com", "the signed-in state names who is signed in"
        assert out["sent"] == {"token": token}
        assert out["member"]["email"] == "other@example.com"
        assert out["orgs"] == ["acme", "globex"]

    def refused(self, token, signed_in_as=None):
        """What the accept view shows for a refused accept: failure()'s state and raw body."""
        sign_in = f'await h.signIn("{signed_in_as}");' if signed_in_as else ""
        signup = "null" if signed_in_as else '{ name: "Nia New", password: "correct horse" }'
        return run_js(
            self.live,
            f"""{sign_in}
            const a = await h.adapter("accept");
            try {{ await a.actions.accept("{token}", {signup}); }}
            catch (e) {{ return a.failure(e, {str(bool(signed_in_as)).lower()}); }}
            throw new Error("the accept went through");""",
            f"/app?view=accept&token={token}",
        )

    @test()
    def test_unknown_invite_is_dead_with_the_raw_404(self, suite_parameter):
        raw = self.server_says(ACCEPT, {"token": "tji_nope", "name": "Nia New", "password": "correct horse"})
        assert body_of(raw)["status"] == 404
        assert self.refused("tji_nope") == {"state": "dead", "raw": raw, "errors": {}}

    @test()
    def test_expired_invite_is_dead_with_the_raw_410(self, suite_parameter):
        created = self.invite("nia@example.com")
        with self.live.env.app.state.sessionmaker() as db:
            past = datetime.now(UTC) - timedelta(seconds=1)
            db.execute(update(Invite).where(Invite.id == created["id"]).values(expires_at=past))
            db.commit()
        shown = self.refused(created["token"])
        assert shown["state"] == "dead"
        assert shown["raw"].startswith("HTTP/1.1 410 Gone\nContent-Type: application/problem+json\n\n")
        assert (body_of(shown["raw"])["status"], body_of(shown["raw"])["detail"]) == (410, "Invite expired")

    @test()
    def test_existing_account_is_the_raw_409_with_sign_in(self, suite_parameter):
        token = self.invite("other@example.com")["token"]
        shown = self.refused(token)
        assert shown["state"] == "exists"
        assert "An account exists for this email; sign in, then accept" in shown["raw"]

    @test()
    def test_short_password_puts_each_message_under_its_field(self, suite_parameter):
        token = self.invite("nia@example.com")["token"]
        out = run_js(
            self.live,
            f"""const a = await h.adapter("accept");
            try {{ await a.actions.accept("{token}", {{ name: "Nia New", password: "short" }}); }}
            catch (e) {{ return a.failure(e, false); }}""",
        )
        assert out["state"] == "short"
        assert body_of(out["raw"])["status"] == 422
        assert "password" in out["errors"] and out["errors"]["password"] in out["raw"]

    @test()
    def test_signed_in_refusal_is_dead_with_the_raw_answer(self, suite_parameter):
        token = self.invite("nia@example.com")["token"]
        shown = self.refused(token, signed_in_as="other@example.com")
        assert shown["state"] == "dead"
        assert body_of(shown["raw"])["status"] == 403

    @test()
    def test_sign_out_ends_the_session(self, suite_parameter):
        out = run_js(
            self.live,
            """await h.signIn();
            await (await h.adapter("context")).signOut();
            const e = await h.fail(h.api.get("/api/v1/me"));
            return { status: e.status, cookies: Object.keys(h.cookies) };""",
            "/app?view=signin",
        )
        assert out == {"status": 401, "cookies": []}
