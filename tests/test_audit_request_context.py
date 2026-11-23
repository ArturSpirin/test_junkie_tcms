"""Audit rows carry the request id and MCP tool from the request being served (api/request_context.py)."""

from sqlalchemy import select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms import audit
from test_junkie_tcms.auth.deps import OrgContext, Principal
from test_junkie_tcms.db.models import Actor, AuditEvent, Org
from tests import support
from tests.catalog_seed import events, ok, url
from tests.execution_seed import run_seed
from tests.support import add_member, login
from tests.test_mcp_server import call, make_admin_token, mcp_client, rpc


@Suite(parameters=support.DATABASES)
class AuditRequestContext:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    @test()
    def test_an_api_write_is_audited_with_its_response_request_id_and_no_tool(self, suite_parameter):
        owner = self.env.owner
        response = owner.patch(url(""), json={"name": "Acme Inc"})
        assert response.status_code == 200, response.text
        request_id = response.headers["x-request-id"]
        assert request_id.startswith("req_") and len(request_id) <= 30  # fits audit_event.request_id
        [event] = events(owner, "org")
        assert (event["request_id"], event["tool"], event["via"]) == (request_id, None, "ui")
        assert owner.get(url("")).headers["x-request-id"] != request_id  # one per request

    @test()
    def test_a_client_request_id_header_is_not_used(self, suite_parameter):
        owner = self.env.owner
        response = owner.patch(url(""), json={"name": "Acme Inc"}, headers={"X-Request-ID": "req_mine"})
        assert response.status_code == 200, response.text
        assert response.headers.get_list("x-request-id") == [response.headers["x-request-id"]]
        assert response.headers["x-request-id"] != "req_mine"
        [event] = events(owner, "org")
        assert event["request_id"] == response.headers["x-request-id"]

    @test()
    def test_an_mcp_tool_call_is_audited_with_the_tool_and_the_mcp_request_id(self, suite_parameter):
        with mcp_client(self.env.app) as mcp:
            owner = self.env.owner
            admin_token = make_admin_token(owner)
            cc = run_seed(owner)["cycle_case"]["id"]
            arguments = {"org": "acme", "id": cc, "status": "success"}
            response = rpc(mcp, admin_token, "tools/call", {"name": "results_create", "arguments": arguments})
            assert response.status_code == 200, response.text
            result = response.json()["result"]["structuredContent"]
            assert result["status"] == 201, result
            [event] = [e for e in events(owner, "result") if e["entity_id"] == result["data"]["id"]]
            assert (event["via"], event["tool"]) == ("mcp", "results_create")
            assert event["request_id"] == response.headers["x-request-id"]  # the client's /mcp request

            again = call(mcp, admin_token, "results_create", **arguments)
            [later] = [e for e in events(owner, "result") if e["entity_id"] == again["data"]["id"]]
            assert later["request_id"] != event["request_id"]

    @test()
    def test_an_invite_accept_is_audited_with_its_request_id(self, suite_parameter):
        # Accept builds its own OrgContext (not get_org_context); the request id still reaches the row.
        owner, globex, invitee = self.env.owner, self.env.client(), self.env.client()
        login(globex, "other@example.com")
        add_member(globex, "ivy@example.com", "viewer", org="globex")
        login(invitee, "ivy@example.com")
        invite = ok(owner.post(url("/invites"), json={"email": "ivy@example.com", "role": "tester"}), 201)
        response = invitee.post("/api/v1/invites:accept", json={"token": invite["token"]})
        assert response.status_code == 200, response.text
        [accepted] = [e for e in events(owner, "invite") if e["action"] == "invite.accept"]
        assert (accepted["request_id"], accepted["tool"]) == (response.headers["x-request-id"], None)

    @test()
    def test_a_row_written_outside_a_request_has_no_request_id_or_tool(self, suite_parameter):
        owner = self.env.owner
        ok(owner.get(url("")))  # signs in, so the owner has an actor
        with self.env.app.state.sessionmaker() as db:
            org = db.scalar(select(Org).where(Org.slug == "acme"))
            actor = db.scalar(select(Actor).where(Actor.org_id == org.id, Actor.kind == "user"))
            ctx = OrgContext(
                org=org,
                actor=actor,
                role="owner",
                scopes=frozenset(),
                principal=Principal(via="api", actor=actor),
            )
            event = audit.record(db, ctx, "org.update", "org", org.id)
            db.commit()
            row = db.get(AuditEvent, event.id)
            assert (row.request_id, row.tool) == (None, None)

    @test()
    def test_audit_q_finds_a_row_by_its_request_id_and_tool(self, suite_parameter):
        owner = self.env.owner
        request_id = owner.patch(url(""), json={"name": "Acme Inc"}).headers["x-request-id"]
        owner.patch(url(""), json={"name": "Acme"})
        found = ok(owner.get(url("/audit"), params={"q": request_id}))["items"]
        assert [(e["action"], e["request_id"]) for e in found] == [("org.update", request_id)]
        with mcp_client(self.env.app) as mcp:
            cc = run_seed(owner)["cycle_case"]["id"]
            call(mcp, make_admin_token(owner), "results_create", org="acme", id=cc, status="success")
        by_tool = ok(owner.get(url("/audit"), params={"q": "results_create"}))["items"]
        assert [e["tool"] for e in by_tool] == ["results_create"]
