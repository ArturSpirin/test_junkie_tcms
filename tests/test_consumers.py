"""T7: consumers pair by device code, heartbeat, upload inventory by hash, and show a derived status."""

from datetime import timedelta

from sqlalchemy import func, select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.api.v1.consumers import roster_hash
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import (
    ApiToken,
    Consumer,
    ConsumerHeartbeat,
    ConsumerInventory,
    PairingRequest,
)
from tests import support
from tests.catalog_seed import events, make_product, ok
from tests.support import add_member, login

ACME = "/api/v1/orgs/acme"
CONSUMER_OPS = {
    "pairings_create": (None, False),
    "pairings_token": (None, False),
    "pairings_approve": ("admin", True),
    "consumers_list": ("read", True),
    "consumers_get": ("read", True),
    "consumers_update": ("admin", True),
    "consumers_revoke": ("admin", True),
    "consumers_heartbeat": ("consumer", False),
    "consumers_put_inventory": ("consumer", False),
}
ROSTER = [{"id": "tests.login.LoginSuite.test_ok", "suite": "LoginSuite"}, {"id": "tests.login.test_bad"}]


class FakeConsumer:
    """Stands in for the test_junkie daemon: pairs, then calls the consumer routes with its token."""

    def __init__(self, env):
        self.env = env
        self.anon = env.client()
        self.client = None

    def start(self) -> dict:
        self.pairing = ok(self.anon.post("/api/v1/pair"), 201)
        return self.pairing

    def poll(self):
        return self.anon.post("/api/v1/pair/token", json={"device_code": self.pairing["device_code"]})

    def claim(self) -> dict:
        token = ok(self.poll())
        self.client = self.env.bearer(token["access_token"])
        return token

    def heartbeat(self, **body):
        body.setdefault("inventory_hashes", {})
        body.setdefault("tj_version", "1.9.0")
        body.setdefault("python", "3.13.1")
        body.setdefault("os", "Linux")
        return self.client.post("/api/v1/consumers/me/heartbeat", json=body)

    def upload(self, project: str, roster: list, digest: str | None = None):
        body = {"hash": digest or roster_hash(roster), "roster": roster}
        return self.client.put(f"/api/v1/consumers/me/inventory/{project}", json=body)


def approve(owner, user_code: str, name: str = "build-box", product_ids=None):
    return owner.post(
        f"{ACME}/pair/approve", json={"user_code": user_code, "name": name, "product_ids": product_ids}
    )


def set_column(app, model, column: str, value, **where):
    with app.state.sessionmaker() as db:
        rows = db.scalars(select(model).filter_by(**where)).all()
        assert rows
        for row in rows:
            setattr(row, column, value)
        db.commit()


def count(app, model) -> int:
    with app.state.sessionmaker() as db:
        return db.scalar(select(func.count()).select_from(model))


@Suite(parameters=support.DATABASES)
class Consumers:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def product(self):
        return make_product(self.env.owner)

    def paired(self, product=None, name: str = "build-box"):
        owner = self.env.owner
        if product is None:
            product = self.product()
        fake = FakeConsumer(self.env)
        fake.start()
        fake.consumer = ok(approve(owner, fake.pairing["user_code"], name, [product["id"]]), 201)
        fake.claim()
        return fake

    def spec(self):
        response = self.env.client().get("/api/v1/openapi.json")
        assert response.status_code == 200
        return {
            op["operationId"]: op
            for path in response.json()["paths"].values()
            for op in path.values()
            if isinstance(op, dict) and "operationId" in op
        }

    # Pairing

    @test()
    def test_device_code_flow_pairs_once(self, suite_parameter):
        owner, product = self.env.owner, self.product()
        fake = FakeConsumer(self.env)
        started = fake.start()
        assert started["expires_in"] == 600 and started["interval"] == 5
        assert len(started["user_code"]) == 9 and started["user_code"][4] == "-"
        pending = fake.poll()
        assert pending.status_code == 428 and pending.json()["error"] == "authorization_pending"

        code = started["user_code"].lower().replace("-", " ")  # typed loosely by the admin
        consumer = ok(approve(owner, code, product_ids=[product["id"]]), 201)
        assert consumer["name"] == "build-box" and consumer["status"] == "offline"
        assert consumer["product_ids"] == [product["id"]]

        token = fake.claim()
        assert token["consumer_id"] == consumer["id"] and token["org"] == "acme"
        again = fake.poll()
        assert again.status_code == 410 and again.json()["error"] == "expired_token"
        assert ok(fake.heartbeat())["inventory_wanted"] == []

    @test()
    def test_only_hashes_of_the_device_code_are_stored(self, suite_parameter):
        app, paired = self.env.app, self.paired()
        with app.state.sessionmaker() as db:
            row = db.scalar(select(PairingRequest))
        assert row.device_code_hash != paired.pairing["device_code"] and len(row.device_code_hash) == 64
        assert row.status == "claimed" and row.org_id is not None

    @test()
    def test_expired_request_fails_approve_and_poll(self, suite_parameter):
        app, owner, product = self.env.app, self.env.owner, self.product()
        fake = FakeConsumer(self.env)
        fake.start()
        set_column(app, PairingRequest, "expires_at", utcnow() - timedelta(seconds=1))
        response = approve(owner, fake.pairing["user_code"], product_ids=[product["id"]])
        assert response.status_code == 410 and response.json()["error"] == "expired_token"
        assert fake.poll().status_code == 410

    @test()
    def test_unknown_codes_are_404(self, suite_parameter):
        owner, product = self.env.owner, self.product()
        assert approve(owner, "BBBB-CCCC", product_ids=[product["id"]]).status_code == 404
        poll = self.env.client().post("/api/v1/pair/token", json={"device_code": "nope"})
        assert poll.status_code == 404 and poll.json()["error"] == "invalid_grant"

    @test()
    def test_approve_rejects_duplicate_names_and_unknown_products(self, suite_parameter):
        owner = self.env.owner
        product = self.product()
        self.paired(product)
        fake = FakeConsumer(self.env)
        code = fake.start()["user_code"]
        assert approve(owner, code, product_ids=[product["id"]]).status_code == 409
        assert approve(owner, code, name="other", product_ids=["01NOPE"]).status_code == 422
        assert approve(owner, code, name="other", product_ids=[]).status_code == 422

    @test()
    def test_non_admin_cannot_approve(self, suite_parameter):
        owner, product = self.env.owner, self.product()
        add_member(owner, "tess@example.com", "tester")
        tester = self.env.client()
        login(tester, "tess@example.com")
        fake = FakeConsumer(self.env)
        code = fake.start()["user_code"]
        assert approve(tester, code, product_ids=[product["id"]]).status_code == 403

    @test()
    def test_pairing_is_rate_limited(self, suite_parameter):
        anon = self.env.client()
        for _ in range(10):
            assert anon.post("/api/v1/pair").status_code == 201
        response = anon.post("/api/v1/pair")
        assert response.status_code == 429 and response.json()["error"] == "slow_down"

    # The consumer token

    @test()
    def test_consumer_token_reaches_no_user_route(self, suite_parameter):
        paired = self.paired()
        for path in ("/api/v1/me", "/api/v1/orgs", f"{ACME}/consumers", f"{ACME}/products"):
            assert paired.client.get(path).status_code == 403, path

    @test()
    def test_consumer_scope_cannot_be_minted_by_hand(self, suite_parameter):
        owner = self.env.owner
        response = owner.post(f"{ACME}/tokens", json={"name": "sneaky", "scopes": ["consumer"]})
        assert response.status_code == 422

    @test()
    def test_other_callers_cannot_use_consumer_routes(self, suite_parameter):
        owner = self.env.owner
        self.paired()
        assert owner.post("/api/v1/consumers/me/heartbeat", json={"inventory_hashes": {}}).status_code == 403
        admin_token = ok(owner.post(f"{ACME}/tokens", json={"name": "ci", "scopes": ["admin"]}), 201)["token"]
        admin = self.env.bearer(admin_token)
        assert admin.post("/api/v1/consumers/me/heartbeat", json={"inventory_hashes": {}}).status_code == 403
        assert (
            admin.put("/api/v1/consumers/me/inventory/p", json={"hash": "0" * 64, "roster": []}).status_code
            == 403
        )
        assert self.env.client().post("/api/v1/consumers/me/heartbeat", json={}).status_code == 401

    @test()
    def test_revoke_disables_the_token(self, suite_parameter):
        owner, paired = self.env.owner, self.paired()
        consumer_id = paired.consumer["id"]
        assert owner.delete(f"{ACME}/consumers/{consumer_id}").status_code == 204
        assert paired.heartbeat().status_code == 401
        assert owner.delete(f"{ACME}/consumers/{consumer_id}").status_code == 204  # twice is a no-op
        assert ok(owner.get(f"{ACME}/consumers"))["items"] == []
        revoked = ok(owner.get(f"{ACME}/consumers", params={"status": "revoked"}))["items"]
        assert [c["status"] for c in revoked] == ["revoked"]
        assert [e["action"] for e in events(owner, "consumer")].count("consumer.revoke") == 1

    @test()
    def test_consumer_stops_when_its_approver_leaves(self, suite_parameter):
        owner, product = self.env.owner, self.product()
        member = add_member(owner, "ada@example.com", "admin")
        ada = self.env.client()
        login(ada, "ada@example.com")
        fake = FakeConsumer(self.env)
        fake.start()
        ok(approve(ada, fake.pairing["user_code"], product_ids=[product["id"]]), 201)
        fake.claim()
        assert fake.heartbeat().status_code == 200
        assert owner.delete(f"{ACME}/members/{member['user_id']}").status_code == 204
        assert fake.heartbeat().status_code == 401

    # Status and history

    @test()
    def test_status_is_derived_from_heartbeats(self, suite_parameter):
        app, owner, paired = self.env.app, self.env.owner, self.paired()
        consumers = f"{ACME}/consumers"
        assert ok(owner.get(consumers))["items"][0]["status"] == "offline"
        ok(paired.heartbeat())
        [row] = ok(owner.get(consumers))["items"]
        assert row["status"] == "online" and row["tj_version"] == "1.9.0" and row["os"] == "Linux"
        assert [c["id"] for c in ok(owner.get(consumers, params={"status": "online"}))["items"]] == [
            row["id"]
        ]
        assert ok(owner.get(consumers, params={"status": "offline"}))["items"] == []

        set_column(app, Consumer, "last_heartbeat_at", utcnow() - timedelta(seconds=91), id=row["id"])
        assert ok(owner.get(consumers))["items"][0]["status"] == "offline"
        assert ok(owner.get(consumers, params={"status": "online"}))["items"] == []

    @test()
    def test_list_filters_by_product(self, suite_parameter):
        owner = self.env.owner
        product = self.product()
        self.paired(product)
        other = make_product(owner, "OPS")
        consumers = f"{ACME}/consumers"
        assert len(ok(owner.get(consumers, params={"product": product["id"]}))["items"]) == 1
        assert ok(owner.get(consumers, params={"product": other["id"]}))["items"] == []

    @test()
    def test_get_returns_24_hours_of_heartbeats(self, suite_parameter):
        app, owner, paired = self.env.app, self.env.owner, self.paired()
        ok(paired.heartbeat())
        set_column(app, ConsumerHeartbeat, "at", utcnow() - timedelta(hours=25))
        ok(paired.heartbeat(busy_job_id="job-1"))  # the server owns busy: the client's value is ignored
        detail = ok(owner.get(f"{ACME}/consumers/{paired.consumer['id']}"))
        assert [b["busy_job_id"] for b in detail["heartbeats"]] == [None]
        assert detail["status"] == "online"
        assert count(app, ConsumerHeartbeat) == 1  # the 25 h old row was pruned

    @test()
    def test_get_is_scoped_to_the_org(self, suite_parameter):
        paired = self.paired()
        other = self.env.client()
        login(other, "other@example.com")
        assert other.get(f"/api/v1/orgs/globex/consumers/{paired.consumer['id']}").status_code == 404

    # Update

    @test()
    def test_rename_is_audited_and_names_stay_unique(self, suite_parameter):
        owner = self.env.owner
        product = self.product()
        paired = self.paired(product)
        consumer_id = paired.consumer["id"]
        renamed = ok(owner.patch(f"{ACME}/consumers/{consumer_id}", json={"name": "nightly-1"}))
        assert renamed["name"] == "nightly-1"
        fake = FakeConsumer(self.env)
        fake.start()
        ok(approve(owner, fake.pairing["user_code"], name="nightly-2", product_ids=[product["id"]]), 201)
        clash = owner.patch(f"{ACME}/consumers/{consumer_id}", json={"name": "nightly-2"})
        assert clash.status_code == 409
        update = next(e for e in events(owner, "consumer") if e["action"] == "consumer.update")
        assert update["changes"]["name"] == {"from": "build-box", "to": "nightly-1"}

    @test()
    def test_name_is_only_what_the_user_sent(self, suite_parameter):
        owner, paired = self.env.owner, self.paired()
        ok(paired.heartbeat(os="Linux build-01.local"))
        assert ok(owner.get(f"{ACME}/consumers/{paired.consumer['id']}"))["name"] == "build-box"

    @test()
    def test_update_products_narrows_the_token(self, suite_parameter):
        app, owner = self.env.app, self.env.owner
        product = self.product()
        paired = self.paired(product)
        other = make_product(owner, "OPS")
        consumer_id = paired.consumer["id"]
        updated = ok(owner.patch(f"{ACME}/consumers/{consumer_id}", json={"product_ids": [other["id"]]}))
        assert updated["product_ids"] == [other["id"]]
        with app.state.sessionmaker() as db:
            consumer = db.get(Consumer, consumer_id)
            assert db.get(ApiToken, consumer.token_id).product_ids == [other["id"]]

    # Inventory

    @test()
    def test_inventory_is_stored_by_hash(self, suite_parameter):
        app, owner, paired = self.env.app, self.env.owner, self.paired()
        digest = roster_hash(ROSTER)
        assert ok(paired.heartbeat(inventory_hashes={"web": digest}))["inventory_wanted"] == ["web"]
        assert ok(paired.upload("web", ROSTER)) == {"changed": True, "test_count": 2}
        audits = len(events(owner, "consumer"))
        with app.state.sessionmaker() as db:
            stamp = db.scalar(select(ConsumerInventory.updated_at))

        assert ok(paired.upload("web", ROSTER)) == {"changed": False, "test_count": 2}
        assert count(app, ConsumerInventory) == 1 and len(events(owner, "consumer")) == audits
        with app.state.sessionmaker() as db:
            assert db.scalar(select(ConsumerInventory.updated_at)) == stamp
        hashes = {"web": digest, "api": "f" * 64}
        assert ok(paired.heartbeat(inventory_hashes=hashes))["inventory_wanted"] == ["api"]

        [summary] = ok(owner.get(f"{ACME}/consumers/{paired.consumer['id']}"))["inventory"]
        assert (summary["project"], summary["hash"], summary["test_count"]) == ("web", digest, 2)

    @test()
    def test_project_count_is_the_inventoried_projects(self, suite_parameter):
        owner = self.env.owner
        product = self.product()
        paired, idle = self.paired(product), self.paired(product, "idle-box")
        ok(paired.upload("web", ROSTER))
        ok(paired.upload("api", ROSTER))
        listed = {c["id"]: c["project_count"] for c in ok(owner.get(f"{ACME}/consumers"))["items"]}
        assert listed == {paired.consumer["id"]: 2, idle.consumer["id"]: 0}
        assert ok(owner.get(f"{ACME}/consumers/{paired.consumer['id']}"))["project_count"] == 2
        renamed = ok(owner.patch(f"{ACME}/consumers/{paired.consumer['id']}", json={"name": "nightly-1"}))
        assert renamed["project_count"] == 2

    @test()
    def test_inventory_hash_must_match_the_roster(self, suite_parameter):
        paired = self.paired()
        assert paired.upload("web", ROSTER, digest="0" * 64).status_code == 422

    # Audit, agents and the contract

    @test()
    def test_every_consumer_operation_is_audited(self, suite_parameter):
        owner, paired = self.env.owner, self.paired()
        consumer_id = paired.consumer["id"]
        ok(paired.upload("web", ROSTER))
        ok(owner.patch(f"{ACME}/consumers/{consumer_id}", json={"name": "renamed"}))
        assert owner.delete(f"{ACME}/consumers/{consumer_id}").status_code == 204
        actions = {e["action"] for e in events(owner, "consumer") if e["entity_id"] == consumer_id}
        expected = {
            "consumer.pair",
            "consumer.token_issue",
            "consumer.inventory",
            "consumer.update",
            "consumer.revoke",
        }
        assert actions == expected

    @test()
    def test_agents_list_excludes_consumers(self, suite_parameter):
        owner = self.env.owner
        self.paired()
        assert ok(owner.get(f"{ACME}/agents"))["items"] == []

    @test(parameters=sorted(CONSUMER_OPS))
    def test_consumer_operation_is_in_the_contract(self, suite_parameter, parameter):
        spec, name = self.spec(), parameter
        scope, mcp = CONSUMER_OPS[name]
        op = spec[name]
        assert (op.get("x-scope"), op["x-toolset"], op["x-mcp"]) == (scope, "consumers", mcp)
