"""`If-Match` guards case edits; `Idempotency-Key` makes a retried org POST return the first result (T3)."""

from datetime import timedelta

from sqlalchemy import func, select, update
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import IdempotencyRecord, Product, TestCase
from tests import support
from tests.catalog_seed import events, ok, seed, url


def seeded(owner):
    """The catalog seed plus one case, PAY-1 (the old `s` fixture)."""
    s = seed(owner)
    s["case"] = ok(
        owner.post(
            url(f"/products/{s['product']['id']}/cases"),
            json={"feature_id": s["child"]["id"], "title": "Pay"},
        ),
        201,
    )
    return s


def count(app, model) -> int:
    with app.state.sessionmaker() as db:
        return db.scalar(select(func.count()).select_from(model))


def create_case(owner, s, key: str | None, title: str = "Retry me"):
    headers = {"Idempotency-Key": key} if key else {}
    body = {"feature_id": s["child"]["id"], "title": title}
    return owner.post(url(f"/products/{s['product']['id']}/cases"), json=body, headers=headers)


@Suite(parameters=support.DATABASES)
class IfMatchIdempotency:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    # If-Match

    @test()
    def test_missing_if_match_is_428(self, suite_parameter):
        owner = self.env.owner
        seeded(owner)
        r = owner.patch(url("/cases/PAY-1"), json={"title": "x"})
        assert r.status_code == 428, r.text
        assert r.headers["content-type"].startswith("application/problem+json")

    @test(parameters=["1", '"1"', 'W/"1"'])
    def test_if_match_forms(self, parameter, suite_parameter):
        owner = self.env.owner
        seeded(owner)
        value = parameter
        r = owner.patch(url("/cases/PAY-1"), json={"title": "x"}, headers={"If-Match": value})
        assert ok(r)["current_version"] == 2

    @test()
    def test_bad_if_match_is_422(self, suite_parameter):
        owner = self.env.owner
        seeded(owner)
        assert (
            owner.patch(url("/cases/PAY-1"), json={"title": "x"}, headers={"If-Match": "abc"}).status_code
            == 422
        )

    @test()
    def test_stale_if_match_is_409_with_the_current_version(self, suite_parameter):
        owner = self.env.owner
        seeded(owner)
        get = owner.get(url("/cases/PAY-1"))
        assert get.headers["ETag"] == '"1"'
        ok(
            owner.patch(
                url("/cases/PAY-1"), json={"title": "first"}, headers={"If-Match": get.headers["ETag"]}
            )
        )
        r = owner.patch(
            url("/cases/PAY-1"), json={"title": "second"}, headers={"If-Match": get.headers["ETag"]}
        )
        assert r.status_code == 409
        assert r.json()["current_version"] == 2
        assert r.headers["ETag"] == '"2"'
        assert ok(owner.get(url("/cases/PAY-1")))["title"] == "first"
        assert len(ok(owner.get(url("/cases/PAY-1/versions")))["items"]) == 2

    @test()
    def test_a_writer_that_lost_the_race_gets_409(self, suite_parameter):
        """The conditional UPDATE refuses a stale version even when the earlier check passed."""
        owner = self.env.owner
        seeded(owner)
        from test_junkie_tcms.api.v1 import cases

        # As if both writers read version 1 before either wrote.
        self.env.patch(cases, "_check_editable", lambda case, expected: None)
        ok(owner.patch(url("/cases/PAY-1"), json={"title": "winner"}, headers={"If-Match": "1"}))
        r = owner.patch(url("/cases/PAY-1"), json={"title": "loser"}, headers={"If-Match": "1"})
        assert r.status_code == 409 and r.json()["current_version"] == 2
        assert ok(owner.get(url("/cases/PAY-1")))["title"] == "winner"

    # Idempotency-Key

    @test()
    def test_replay_returns_the_first_result_without_a_duplicate(self, suite_parameter):
        owner = self.env.owner
        s = seeded(owner)
        app = self.env.app
        first = create_case(owner, s, "k-1")
        assert first.status_code == 201 and "Idempotent-Replayed" not in first.headers
        again = create_case(owner, s, "k-1")
        assert again.status_code == 201
        assert again.headers["Idempotent-Replayed"] == "true"
        assert again.json() == first.json()
        assert again.headers["ETag"] == first.headers["ETag"]
        assert again.headers["Location"] == first.headers["Location"]
        assert count(app, TestCase) == 2
        assert [e["action"] for e in events(owner, "test_case")].count("case.create") == 2

    @test()
    def test_same_key_with_another_body_is_422(self, suite_parameter):
        owner = self.env.owner
        s = seeded(owner)
        app = self.env.app
        ok(create_case(owner, s, "k-2"), 201)
        assert create_case(owner, s, "k-2", title="Something else").status_code == 422
        assert count(app, TestCase) == 2

    @test()
    def test_keys_are_per_actor(self, suite_parameter):
        owner = self.env.owner
        s = seeded(owner)
        app = self.env.app
        from tests.support import add_member, login

        add_member(owner, "ed@example.com", "editor")
        editor = self.env.client()
        login(editor, "ed@example.com")
        ok(create_case(owner, s, "shared"), 201)
        r = create_case(editor, s, "shared")
        assert r.status_code == 201 and "Idempotent-Replayed" not in r.headers
        assert count(app, TestCase) == 3

    @test()
    def test_without_a_key_every_post_runs(self, suite_parameter):
        owner = self.env.owner
        s = seeded(owner)
        app = self.env.app
        ok(create_case(owner, s, None), 201)
        ok(create_case(owner, s, None), 201)
        assert count(app, TestCase) == 3
        assert count(app, IdempotencyRecord) == 0

    @test()
    def test_an_error_is_not_recorded_so_a_fixed_retry_runs(self, suite_parameter):
        owner = self.env.owner
        s = seeded(owner)
        app = self.env.app
        body = {"feature_id": "missing", "title": "x"}
        headers = {"Idempotency-Key": "k-err"}
        path = url(f"/products/{s['product']['id']}/cases")
        assert owner.post(path, json=body, headers=headers).status_code == 422
        assert count(app, IdempotencyRecord) == 0
        assert owner.post(path, json=body, headers=headers).status_code == 422

    @test()
    def test_pending_key_is_409_and_points_to_the_resource(self, suite_parameter):
        owner = self.env.owner
        s = seeded(owner)
        app = self.env.app
        ok(create_case(owner, s, "k-3"), 201)
        with app.state.sessionmaker() as db:
            db.execute(update(IdempotencyRecord).values(state="pending"))
            db.commit()
        r = create_case(owner, s, "k-3")
        assert r.status_code == 409
        assert "read the resource" in r.json()["detail"]

    @test()
    def test_an_expired_key_is_reused_in_place(self, suite_parameter):
        owner = self.env.owner
        s = seeded(owner)
        app = self.env.app
        ok(create_case(owner, s, "k-4"), 201)
        with app.state.sessionmaker() as db:
            db.execute(update(IdempotencyRecord).values(expires_at=utcnow() - timedelta(seconds=1)))
            db.commit()
            first_id = db.scalar(select(IdempotencyRecord.id))
        again = create_case(owner, s, "k-4", title="A new request")
        assert again.status_code == 201 and "Idempotent-Replayed" not in again.headers
        with app.state.sessionmaker() as db:
            records = list(db.scalars(select(IdempotencyRecord)))
        assert [(r.id, r.state) for r in records] == [(first_id, "done")]
        assert count(app, TestCase) == 3

    @test()
    def test_retrofitted_catalog_post_replays(self, suite_parameter):
        owner = self.env.owner
        seeded(owner)
        app = self.env.app
        headers = {"Idempotency-Key": "p-1"}
        first = owner.post(url("/products"), json={"key": "SHOP", "name": "Shop"}, headers=headers)
        again = owner.post(url("/products"), json={"key": "SHOP", "name": "Shop"}, headers=headers)
        assert first.status_code == again.status_code == 201
        assert again.headers["Idempotent-Replayed"] == "true" and again.json() == first.json()
        assert count(app, Product) == 2
        # A no-op archive commits too, so its key is recorded and replays.
        archive = url(f"/products/{first.json()['id']}/archive")
        ok(owner.post(archive))
        noop = owner.post(archive, headers={"Idempotency-Key": "a-1"})
        assert noop.status_code == 200
        assert (
            owner.post(archive, headers={"Idempotency-Key": "a-1"}).headers["Idempotent-Replayed"] == "true"
        )

    @test()
    def test_members_add_replay_holds_no_secret(self, suite_parameter):
        owner = self.env.owner
        seeded(owner)
        app = self.env.app
        body = {"email": "new@example.com", "name": "New", "role": "viewer", "password": "a secret password"}
        headers = {"Idempotency-Key": "m-1"}
        ok(owner.post(url("/members"), json=body, headers=headers), 201)
        again = owner.post(url("/members"), json=body, headers=headers)
        assert again.headers["Idempotent-Replayed"] == "true"
        with app.state.sessionmaker() as db:
            stored = [r.response_body for r in db.scalars(select(IdempotencyRecord))]
        assert stored and "a secret password" not in str(stored) and "password" not in str(stored)

    @test()
    def test_tokens_create_ignores_idempotency_key(self, suite_parameter):
        owner = self.env.owner
        seeded(owner)
        app = self.env.app
        body = {"name": "ci", "scopes": ["read"]}
        headers = {"Idempotency-Key": "t-1"}
        a = ok(owner.post(url("/tokens"), json=body, headers=headers), 201)
        b = ok(owner.post(url("/tokens"), json=body, headers=headers), 201)
        assert a["token"] != b["token"]
        assert count(app, IdempotencyRecord) == 0
