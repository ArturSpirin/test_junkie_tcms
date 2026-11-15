"""`sweep-idempotency` deletes expired `Idempotency-Key` records in batches; reuse after it stays correct."""

import contextlib
import io
from datetime import timedelta

from sqlalchemy import func, select, update
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms import cli
from test_junkie_tcms.api import idempotency
from test_junkie_tcms.api.idempotency import PENDING_GRACE, sweep_expired
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import IdempotencyRecord, TestCase
from tests import support
from tests.catalog_seed import ok, seed, url


def create_case(owner, s, key: str, title: str = "Retry me"):
    body = {"feature_id": s["child"]["id"], "title": title}
    path = url(f"/products/{s['product']['id']}/cases")
    return owner.post(path, json=body, headers={"Idempotency-Key": key})


def count(app, model) -> int:
    with app.state.sessionmaker() as db:
        return db.scalar(select(func.count()).select_from(model))


def keys(app) -> list[str]:
    with app.state.sessionmaker() as db:
        return sorted(db.scalars(select(IdempotencyRecord.key)))


def set_record(app, key: str, **values) -> None:
    with app.state.sessionmaker() as db:
        db.execute(update(IdempotencyRecord).where(IdempotencyRecord.key == key).values(**values))
        db.commit()


def expire(app, key: str, ago: timedelta = timedelta(seconds=1), **values) -> None:
    set_record(app, key, expires_at=utcnow() - ago, **values)


@Suite(parameters=support.DATABASES)
class IdempotencySweep:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def s(self):
        return seed(self.env.owner)

    @test()
    def test_deletes_expired_records_in_batches(self, suite_parameter):
        owner, s, app = self.env.owner, self.s(), self.env.app
        for i in range(5):
            ok(create_case(owner, s, f"k-{i}", title=f"Case {i}"), 201)
            expire(app, f"k-{i}", ago=timedelta(minutes=10 - i))
        assert sweep_expired(app.state.sessionmaker, batch_size=2, max_batches=1) == 2
        assert keys(app) == ["k-2", "k-3", "k-4"]  # oldest first
        assert sweep_expired(app.state.sessionmaker, batch_size=2) == 3
        assert count(app, IdempotencyRecord) == 0

    @test()
    def test_batch_size_must_be_positive(self, suite_parameter):
        app = self.env.app
        with support.raises(ValueError):
            sweep_expired(app.state.sessionmaker, batch_size=0)

    @test()
    def test_keeps_unexpired_and_recent_pending_records(self, suite_parameter):
        owner, s, app = self.env.owner, self.s(), self.env.app
        for key in ("live", "pending-recent", "pending-old", "done-old"):
            ok(create_case(owner, s, key, title=key), 201)
        expire(app, "pending-recent", ago=PENDING_GRACE - timedelta(minutes=5), state="pending")
        expire(app, "pending-old", ago=PENDING_GRACE + timedelta(minutes=5), state="pending")
        expire(app, "done-old")
        assert sweep_expired(app.state.sessionmaker) == 2
        assert keys(app) == ["live", "pending-recent"]

    @test()
    def test_cli_sweeps_and_prints_the_count(self, suite_parameter):
        owner, s, app, settings = self.env.owner, self.s(), self.env.app, self.env.settings
        ok(create_case(owner, s, "k-cli"), 201)
        ok(create_case(owner, s, "k-keep", title="Keep"), 201)
        expire(app, "k-cli")
        self.env.setenv("TJ_TCMS_DATABASE_URL", settings.database_url)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["sweep-idempotency", "--batch-size", "10"])
        assert out.getvalue().strip() == "Deleted 1 expired idempotency records"
        assert keys(app) == ["k-keep"]

    @test()
    def test_a_replay_inside_the_window_still_works_after_a_sweep(self, suite_parameter):
        owner, s, app = self.env.owner, self.s(), self.env.app
        first = ok(create_case(owner, s, "k-live"), 201)
        ok(create_case(owner, s, "k-old", title="Old"), 201)
        expire(app, "k-old")
        assert sweep_expired(app.state.sessionmaker) == 1
        again = create_case(owner, s, "k-live")
        assert again.status_code == 201 and again.headers["Idempotent-Replayed"] == "true"
        assert again.json() == first
        assert count(app, TestCase) == 2

    @test()
    def test_a_swept_key_sent_again_is_recorded_fresh(self, suite_parameter):
        owner, s, app = self.env.owner, self.s(), self.env.app
        first = ok(create_case(owner, s, "k-1"), 201)
        with app.state.sessionmaker() as db:
            first_id = db.scalar(select(IdempotencyRecord.id))
        expire(app, "k-1")
        assert sweep_expired(app.state.sessionmaker) == 1
        again = create_case(owner, s, "k-1", title="A new request")
        assert again.status_code == 201 and "Idempotent-Replayed" not in again.headers
        assert again.json()["id"] != first["id"]
        with app.state.sessionmaker() as db:
            records = list(db.scalars(select(IdempotencyRecord)))
        assert len(records) == 1 and records[0].id != first_id and records[0].state == "done"

    @test()
    def test_a_record_swept_between_lookup_and_claim_is_recorded_fresh(self, suite_parameter):
        owner, s, app = self.env.owner, self.s(), self.env.app
        ok(create_case(owner, s, "k-race"), 201)
        expire(app, "k-race")
        real_claim = idempotency._claim

        def swept_first(db, rec, fresh, now):
            assert sweep_expired(app.state.sessionmaker) == 1
            return real_claim(db, rec, fresh, now)

        self.env.patch(idempotency, "_claim", swept_first)
        r = create_case(owner, s, "k-race", title="After the sweep")
        assert r.status_code == 201 and "Idempotent-Replayed" not in r.headers
        assert keys(app) == ["k-race"]
        assert count(app, TestCase) == 2

    @test()
    def test_a_record_claimed_by_another_request_first_is_409(self, suite_parameter):
        owner, s, app = self.env.owner, self.s(), self.env.app
        ok(create_case(owner, s, "k-claimed"), 201)
        expire(app, "k-claimed")
        real_claim = idempotency._claim

        def claimed_first(db, rec, fresh, now):
            # Another request with the same key and body claims the expired row and is still running.
            set_record(app, "k-claimed", state="pending", expires_at=now + idempotency.TTL)
            return real_claim(db, rec, fresh, now)

        self.env.patch(idempotency, "_claim", claimed_first)
        r = create_case(owner, s, "k-claimed")
        assert r.status_code == 409, r.text
        assert count(app, TestCase) == 1
