"""F2: the actor directory members read, last active, agent description and enable."""

from datetime import timedelta

from sqlalchemy import select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.base import aware, utcnow
from test_junkie_tcms.db.models import Actor, AuditEvent, Consumer
from tests import support
from tests.catalog_seed import make_product, ok, url
from tests.support import add_member, login
from tests.test_consumers import FakeConsumer, approve


def _agent(owner, **body) -> dict:
    body.setdefault("name", "bot")
    body.setdefault("role", "viewer")
    return ok(owner.post(url("/agents"), json=body), 201)


def _last_active(app, actor_id: str):
    with app.state.sessionmaker() as db:
        value = db.get(Actor, actor_id).last_active_at
        return aware(value) if value else None


def _set_last_active(app, actor_id: str, value) -> None:
    with app.state.sessionmaker() as db:
        db.get(Actor, actor_id).last_active_at = value
        db.commit()


@Suite(parameters=support.DATABASES)
class Actors:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def viewer(self) -> tuple[dict, object]:
        member = add_member(self.env.owner, "vic@example.com", "viewer")
        client = self.env.client()
        login(client, "vic@example.com")
        return member, client

    @test()
    def test_a_viewer_reads_every_actor_and_token_name(self, suite_parameter):
        owner = self.env.owner
        member, viewer = self.viewer()
        agent = _agent(owner, name="nightly-bot")
        token = ok(owner.post(url("/tokens"), json={"name": "ci", "scopes": ["read"]}), 201)
        fake = FakeConsumer(self.env)
        fake.start()
        consumer = ok(
            approve(owner, fake.pairing["user_code"], "build-box", [make_product(owner)["id"]]), 201
        )
        fake.claim()

        assert viewer.get(url("/agents")).status_code == 403  # the admin list stays admin only
        directory = ok(viewer.get(url("/actors")))
        kinds = {a["name"]: a["kind"] for a in directory["actors"]}
        assert kinds["Vic"] == "user" and kinds["nightly-bot"] == "agent" and kinds["build-box"] == "consumer"
        assert sum(1 for kind in kinds.values() if kind == "user") == 2
        by_id = {a["id"]: a for a in directory["actors"]}
        assert by_id[member["actor_id"]]["disabled"] is False and agent["id"] in by_id
        tokens = {t["name"]: t for t in directory["tokens"]}
        assert tokens["ci"]["id"] == token["id"]
        assert consumer["name"] == "build-box"
        assert "@" not in viewer.get(url("/actors")).text  # names only, never emails

    @test()
    def test_disabled_agents_removed_members_and_revoked_consumers_show_disabled(self, suite_parameter):
        owner = self.env.owner
        member, _ = self.viewer()
        agent = _agent(owner)
        ok(owner.post(url(f"/agents/{agent['id']}/disable")))
        fake = FakeConsumer(self.env)
        fake.start()
        consumer = ok(
            approve(owner, fake.pairing["user_code"], "build-box", [make_product(owner)["id"]]), 201
        )
        assert owner.delete(url(f"/consumers/{consumer['id']}")).status_code == 204
        assert owner.delete(url(f"/members/{member['user_id']}")).status_code == 204

        by_name = {a["name"]: a for a in ok(owner.get(url("/actors")))["actors"]}
        assert by_name["bot"]["disabled"] and by_name["Vic"]["disabled"] and by_name["build-box"]["disabled"]

    @test()
    def test_a_read_only_get_sets_last_active(self, suite_parameter):
        app = self.env.app
        member, viewer = self.viewer()
        assert _last_active(app, member["actor_id"]) is None
        before = utcnow()
        ok(viewer.get(url("/actors")))
        touched = _last_active(app, member["actor_id"])
        assert touched is not None and touched >= before - timedelta(seconds=1)
        [row] = [m for m in ok(viewer.get(url("/members")))["items"] if m["user_id"] == member["user_id"]]
        assert row["last_active_at"] is not None

    @test()
    def test_last_active_is_written_at_most_once_a_minute(self, suite_parameter):
        app = self.env.app
        member, viewer = self.viewer()
        recent = utcnow() - timedelta(seconds=10)
        _set_last_active(app, member["actor_id"], recent)
        ok(viewer.get(url("/actors")))
        assert _last_active(app, member["actor_id"]) == aware(recent)
        stale = utcnow() - timedelta(minutes=5)
        _set_last_active(app, member["actor_id"], stale)
        ok(viewer.get(url("/actors")))
        assert _last_active(app, member["actor_id"]) > aware(stale) + timedelta(minutes=4)

    @test()
    def test_an_agent_token_marks_the_agent_active(self, suite_parameter):
        owner, app = self.env.owner, self.env.app
        agent = _agent(owner)
        token = ok(
            owner.post(url("/tokens"), json={"name": "t", "scopes": ["read"], "actor_id": agent["id"]}), 201
        )
        assert _last_active(app, agent["id"]) is None
        ok(self.env.bearer(token["token"]).get(url("/actors")))
        assert _last_active(app, agent["id"]) is not None
        [row] = [a for a in ok(owner.get(url("/agents")))["items"] if a["id"] == agent["id"]]
        assert row["last_active_at"] is not None

    @test()
    def test_agent_description_round_trips_and_clears(self, suite_parameter):
        owner = self.env.owner
        agent = _agent(owner, description="Runs the nightly suite")
        assert agent["description"] == "Runs the nightly suite"
        updated = ok(owner.patch(url(f"/agents/{agent['id']}"), json={"description": "Nightly and weekly"}))
        assert updated["description"] == "Nightly and weekly"
        assert ok(owner.patch(url(f"/agents/{agent['id']}"), json={"description": ""}))["description"] is None
        too_long = owner.post(url("/agents"), json={"name": "b2", "role": "viewer", "description": "x" * 501})
        assert too_long.status_code == 422

    @test()
    def test_enable_turns_a_disabled_agent_back_on_and_is_audited(self, suite_parameter):
        owner, app = self.env.owner, self.env.app
        agent = _agent(owner)
        ok(owner.post(url(f"/agents/{agent['id']}/disable")))
        enabled = ok(owner.post(url(f"/agents/{agent['id']}/enable")))
        assert enabled["disabled_at"] is None
        assert ok(owner.post(url(f"/agents/{agent['id']}/enable")))["disabled_at"] is None  # idempotent
        with app.state.sessionmaker() as db:
            actions = [
                e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_id == agent["id"]))
            ]
        assert actions.count("agent.enable") == 1

    @test()
    def test_enable_is_422_once_the_owner_has_left_and_admin_only(self, suite_parameter):
        owner = self.env.owner
        member = add_member(owner, "ada@example.com", "admin")
        agent = _agent(owner, owner_user_id=member["user_id"])
        ok(owner.post(url(f"/agents/{agent['id']}/disable")))
        assert owner.delete(url(f"/members/{member['user_id']}")).status_code == 204
        response = owner.post(url(f"/agents/{agent['id']}/enable"))
        assert response.status_code == 422, response.text
        _, viewer = self.viewer()
        assert viewer.post(url(f"/agents/{agent['id']}/enable")).status_code == 403

    @test()
    def test_a_consumer_actor_cant_be_enabled_as_an_agent(self, suite_parameter):
        owner = self.env.owner
        fake = FakeConsumer(self.env)
        fake.start()
        consumer = ok(
            approve(owner, fake.pairing["user_code"], "build-box", [make_product(owner)["id"]]), 201
        )
        with self.env.app.state.sessionmaker() as db:
            actor_id = db.get(Consumer, consumer["id"]).actor_id
        assert owner.post(url(f"/agents/{actor_id}/enable")).status_code == 404
