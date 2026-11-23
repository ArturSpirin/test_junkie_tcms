"""T8: automated cycles split cases between people and consumers; consumers claim jobs, report results, and
lose them when they stop beating."""

from datetime import timedelta

from sqlalchemy import select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.api.v1 import consumers, cycles, job_queue, jobs, results
from test_junkie_tcms.db.base import utcnow
from test_junkie_tcms.db.models import Consumer, Cycle, Job
from tests import support
from tests.catalog_seed import events, ok, seed, url
from tests.execution_seed import cycle_cases, make_case
from tests.support import add_member, login
from tests.test_consumers import ROSTER, FakeConsumer, approve, count, set_column

REF_OK, REF_BAD = ROSTER[0]["id"], ROSTER[1]["id"]
JOB_OPS = {
    "jobs_next": ("consumer", False),
    "jobs_report": ("consumer", False),
    "jobs_list": ("read", True),
    "jobs_cancel": ("write:execution", True),
    "jobs_reassign": ("write:execution", True),
}


class Clock:
    def __init__(self):
        self.now = utcnow()

    def __call__(self):
        return self.now

    def tick(self, seconds: int):
        self.now += timedelta(seconds=seconds)


def make_clock(env):
    c = Clock()
    for module in (cycles, consumers, jobs, results):
        env.patch(module, "utcnow", c)
    return c


def make_world(env, owner, clock):
    s = seed(owner)
    p, f = s["product"]["id"], s["child"]["id"]
    cases = {
        "ok": make_case(owner, p, f, "Login ok", automation="automated", automation_ref=REF_OK),
        "bad": make_case(owner, p, f, "Login bad", automation="automated", automation_ref=REF_BAD),
        "manual": make_case(owner, p, f, "Looks right"),
        "unknown": make_case(
            owner, p, f, "Not listed", automation="automated", automation_ref="tests.x.test_y"
        ),
    }
    fakes = []
    for name in ("box-a", "box-b"):
        fake = FakeConsumer(env)
        fake.start()
        fake.consumer = ok(approve(owner, fake.pairing["user_code"], name, product_ids=[p]), 201)
        fake.claim()
        ok(fake.upload("web", ROSTER))
        ok(fake.heartbeat())
        fakes.append(fake)
    return {"product": p, "cases": cases, "a": fakes[0], "b": fakes[1]}


def source(world, *consumer_list, mode="both", **body):
    body.setdefault("case_ids", [c["id"] for c in world["cases"].values()])
    return {"mode": mode, "consumer_ids": [c.consumer["id"] for c in consumer_list], **body}


def create(owner, world, *consumer_list, **body):
    return owner.post(
        url(f"/products/{world['product']}/cycles"),
        json={"name": "Nightly", **source(world, *consumer_list, **body)},
    )


def job_list(owner, cycle_id: str) -> list[dict]:
    return ok(owner.get(url(f"/cycles/{cycle_id}/jobs")))["items"]


def next_job(fake, wait: int = 0):
    return fake.client.get("/api/v1/consumers/me/jobs/next", params={"wait": wait})


def report(fake, job_id: str, state: str, *items, **extra):
    body = {"state": state, "results": [{"ref": r, "status": s} for r, s in items], **extra}
    return fake.client.post(f"/api/v1/consumers/me/jobs/{job_id}/state", json=body)


def statuses(owner, cycle_id: str) -> dict[str, tuple]:
    return {
        cc["case_id"]: (cc["runner"], cc["consumer_id"], cc["status"]) for cc in cycle_cases(owner, cycle_id)
    }


def consumer_status(owner, fake) -> str:
    return ok(owner.get(url(f"/consumers/{fake.consumer['id']}")))["status"]


def make_spec(client_factory):
    response = client_factory().get("/api/v1/openapi.json")
    assert response.status_code == 200
    return {
        op["operationId"]: op
        for path in response.json()["paths"].values()
        for op in path.values()
        if isinstance(op, dict) and "operationId" in op
    }


@Suite(parameters=support.DATABASES)
class Jobs:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    # Start

    @test()
    def test_preview_counts_runners_and_writes_nothing(self, suite_parameter):
        app = self.env.app
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a, b = world["a"], world["b"]
        before = (count(app, Cycle), count(app, Job))
        preview = ok(
            owner.post(url(f"/products/{world['product']}/cycles/preview"), json=source(world, a, b))
        )
        assert preview["total"] == 4 and preview["unmatched"] == 1
        assert preview["runners"]["person"] == 2
        assert [(c["name"], c["cases"], c["jobs"]) for c in preview["runners"]["consumers"]] == [
            ("box-a", 1, 1),
            ("box-b", 1, 1),
        ]
        assert (count(app, Cycle), count(app, Job)) == before
        manual = ok(owner.post(url(f"/products/{world['product']}/cycles/preview"), json={"case_ids": []}))
        assert manual["runners"] == {"person": 0, "consumers": []}

    @test()
    def test_create_splits_cases_by_inventory(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a, b = world["a"], world["b"]
        cycle = ok(create(owner, world, a, b), 201)
        assert cycle["mode"] == "both"
        cases, aid, bid = world["cases"], a.consumer["id"], b.consumer["id"]
        assert statuses(owner, cycle["id"]) == {
            cases["ok"]["id"]: ("consumer", aid, "untested"),
            cases["bad"]["id"]: ("consumer", bid, "untested"),
            cases["manual"]["id"]: ("person", None, "untested"),
            cases["unknown"]["id"]: ("person", None, "untested"),
        }
        listed = job_list(owner, cycle["id"])
        assert sorted(
            (j["consumer_id"], j["project"], tuple(j["refs"]), j["status"]) for j in listed
        ) == sorted([(aid, "web", (REF_OK,), "queued"), (bid, "web", (REF_BAD,), "queued")])

    @test()
    def test_create_refuses_bad_consumer_choices(self, suite_parameter):
        app = self.env.app
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        set_column(app, Consumer, "last_heartbeat_at", utcnow() - timedelta(minutes=5), id=a.consumer["id"])
        response = create(owner, world, a)
        assert response.status_code == 409 and "offline" in response.text
        assert create(owner, world, mode="automated").status_code == 422
        assert create(owner, world, world["b"], mode="manual").status_code == 422
        assert create(owner, world, mode="both", consumer_ids=["01NOPE"]).status_code == 404
        assert count(app, Cycle) == 0

    # Claim and report

    @test()
    def test_consumer_claims_reports_and_cases_update(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        cycle = ok(create(owner, world, a), 201)
        job = ok(next_job(a))
        assert job["status"] == "claimed" and job["refs"] == [REF_OK, REF_BAD]
        assert ok(next_job(a))["id"] == job["id"]  # a held job comes back
        assert consumer_status(owner, a) == "busy"

        ok(report(a, job["id"], "running", (REF_OK, "success")))
        done = ok(report(a, job["id"], "done", (REF_BAD, "fail"), ("tests.nope", "success")))
        assert (
            done["job"]["status"] == "done" and done["recorded"] == 1 and done["unmatched"] == ["tests.nope"]
        )
        cases = world["cases"]
        got = statuses(owner, cycle["id"])
        assert got[cases["ok"]["id"]][2] == "success" and got[cases["bad"]["id"]][2] == "fail"
        assert got[cases["manual"]["id"]][2] == "untested"
        assert consumer_status(owner, a) == "online"
        assert report(a, job["id"], "done").status_code == 409
        assert next_job(a).status_code == 204
        assert report(world["b"], job["id"], "done").status_code == 404

    @test()
    def test_failed_job_cancels_the_cases_it_did_not_report(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        cycle = ok(create(owner, world, a), 201)
        job = ok(next_job(a))
        ok(report(a, job["id"], "failed", (REF_OK, "success")))
        got = statuses(owner, cycle["id"])
        assert got[world["cases"]["bad"]["id"]][2] == "cancel"

    @test()
    def test_rejected_job_keeps_its_reason_and_cancels_its_cases(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        cycle = ok(create(owner, world, a), 201)
        job = ok(next_job(a))
        assert report(a, job["id"], "rejected").status_code == 422  # a rejection says why
        done = ok(report(a, job["id"], "rejected", reason="project web is not checked out"))
        assert (done["job"]["status"], done["job"]["reason"]) == (
            "rejected",
            "project web is not checked out",
        )
        assert consumer_status(owner, a) == "online"
        got = statuses(owner, cycle["id"])
        assert got[world["cases"]["ok"]["id"]][2] == got[world["cases"]["bad"]["id"]][2] == "cancel"
        cc = next(c for c in cycle_cases(owner, cycle["id"]) if c["case_id"] == world["cases"]["ok"]["id"])
        [result] = ok(owner.get(url(f"/cycle-cases/{cc['id']}/results"), params={"mode": "markdown"}))[
            "items"
        ]
        assert "project web is not checked out" in str(result["comment"])
        assert [j["status"] for j in job_list(owner, cycle["id"])] == ["rejected"]  # not requeued

    # Jobs per machine, pause

    @test()
    def test_consumer_jobs_list_newest_first_with_reasons(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        cid = a.consumer["id"]
        first = ok(create(owner, world, a), 201)
        rejected = ok(next_job(a))
        ok(report(a, rejected["id"], "rejected", reason="no browser"))
        ok(create(owner, world, a), 201)
        listed = ok(owner.get(url(f"/consumers/{cid}/jobs")))
        assert [j["status"] for j in listed["items"]] == ["queued", "rejected"] and listed["total"] == 2
        assert listed["items"][1]["cycle_id"] == first["id"] and listed["items"][1]["reason"] == "no browser"
        only = ok(owner.get(url(f"/consumers/{cid}/jobs"), params={"status": "rejected"}))["items"]
        assert [j["id"] for j in only] == [rejected["id"]]
        assert owner.get(url(f"/consumers/{cid}/jobs"), params={"status": "nope"}).status_code == 422
        detail = ok(owner.get(url(f"/consumers/{cid}")))
        assert (detail["jobs_today"], detail["rejected_today"]) == (2, 1)
        assert ok(owner.get(url(f"/consumers/{world['b'].consumer['id']}/jobs")))["items"] == []

    @test()
    def test_paused_consumer_keeps_its_job_and_takes_no_new_one(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        cid = a.consumer["id"]
        ok(create(owner, world, a), 201)
        held = ok(next_job(a))
        ok(create(owner, world, a), 201)
        paused = ok(owner.post(url(f"/consumers/{cid}/pause")))
        assert paused["paused_at"] is not None
        ok(owner.post(url(f"/consumers/{cid}/pause")))  # no-op
        assert ok(next_job(a))["id"] == held["id"]  # the held job runs to the end
        ok(report(a, held["id"], "done"))
        assert next_job(a).status_code == 204
        response = create(owner, world, a)
        assert response.status_code == 409 and response.json()["code"] == "consumer_paused"
        actions = [e["action"] for e in events(owner, "consumer") if e["entity_id"] == cid]
        assert actions.count("consumer.pause") == 1
        assert ok(owner.post(url(f"/consumers/{cid}/resume")))["paused_at"] is None
        assert ok(next_job(a))["status"] == "claimed"
        assert "consumer.resume" in [e["action"] for e in events(owner, "consumer")]

    @test()
    def test_stall_skips_a_paused_consumer(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a, b = world["a"], world["b"]
        cycle = ok(create(owner, world, a), 201)
        ok(next_job(a))
        ok(owner.post(url(f"/consumers/{b.consumer['id']}/pause")))
        clock.tick(121)
        ok(b.heartbeat())
        [failed] = job_list(owner, cycle["id"])
        assert (failed["status"], failed["reason"]) == ("failed", "consumer lost")

    @test()
    def test_pause_and_resume_need_admin_and_a_live_consumer(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        cid = world["a"].consumer["id"]
        add_member(owner, "tess@example.com", "tester")
        tester = self.env.client()
        login(tester, "tess@example.com")
        assert tester.post(url(f"/consumers/{cid}/pause")).status_code == 403
        assert owner.delete(url(f"/consumers/{cid}")).status_code == 204
        assert owner.post(url(f"/consumers/{cid}/pause")).status_code == 409
        assert owner.post(url(f"/consumers/{cid}/resume")).status_code == 409

    # Cancel and reassign

    @test()
    def test_cancel_a_queued_and_a_held_job(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a, b = world["a"], world["b"]
        cycle = ok(create(owner, world, a, b), 201)
        by_consumer = {j["consumer_id"]: j for j in job_list(owner, cycle["id"])}
        queued, held = by_consumer[b.consumer["id"]], by_consumer[a.consumer["id"]]
        ok(next_job(a))
        assert ok(owner.post(url(f"/jobs/{queued['id']}/cancel")))["status"] == "cancelled"
        assert ok(owner.post(url(f"/jobs/{held['id']}/cancel")))["status"] == "cancelled"
        assert owner.post(url(f"/jobs/{held['id']}/cancel")).status_code == 409
        assert ok(a.heartbeat())["cancel_job_ids"] == [held["id"]]
        assert ok(a.heartbeat())["cancel_job_ids"] == []
        assert ok(b.heartbeat())["cancel_job_ids"] == []
        got = statuses(owner, cycle["id"])
        assert got[world["cases"]["ok"]["id"]][2] == got[world["cases"]["bad"]["id"]][2] == "cancel"
        assert consumer_status(owner, a) == "online"

    @test()
    def test_reassign_moves_a_queued_job_and_its_cases(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a, b = world["a"], world["b"]
        cycle = ok(create(owner, world, a), 201)
        [job] = job_list(owner, cycle["id"])
        moved = ok(owner.post(url(f"/jobs/{job['id']}/reassign"), json={"consumer_id": b.consumer["id"]}))
        assert moved["consumer_id"] == b.consumer["id"]
        assert {cc[1] for cc in statuses(owner, cycle["id"]).values() if cc[0] == "consumer"} == {
            b.consumer["id"]
        }
        assert next_job(a).status_code == 204
        assert ok(next_job(b))["id"] == job["id"]
        again = owner.post(url(f"/jobs/{job['id']}/reassign"), json={"consumer_id": a.consumer["id"]})
        assert again.status_code == 409

    # Stalls, with a fake clock

    @test()
    def test_stalled_job_is_requeued_once_then_its_cases_cancel(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a, b = world["a"], world["b"]
        cycle = ok(create(owner, world, a), 201)
        job = ok(next_job(a))
        clock.tick(121)
        ok(b.heartbeat())  # b's beat runs the stall check: a has been silent for 121 s
        [requeued] = job_list(owner, cycle["id"])
        assert (requeued["status"], requeued["consumer_id"], requeued["attempts"]) == (
            "queued",
            b.consumer["id"],
            2,
        )
        assert ok(next_job(b))["id"] == job["id"]
        clock.tick(121)
        ok(a.heartbeat())
        [failed] = job_list(owner, cycle["id"])
        assert (failed["status"], failed["reason"]) == ("failed", "consumer lost")
        got = statuses(owner, cycle["id"])
        assert got[world["cases"]["ok"]["id"]][2] == got[world["cases"]["bad"]["id"]][2] == "cancel"
        cc = next(c for c in cycle_cases(owner, cycle["id"]) if c["case_id"] == world["cases"]["ok"]["id"])
        [result] = ok(owner.get(url(f"/cycle-cases/{cc['id']}/results"), params={"mode": "markdown"}))[
            "items"
        ]
        assert "consumer lost" in str(result["comment"]) and result["via"] == "consumer"

    @test()
    def test_heartbeat_just_after_the_stall_window_keeps_the_job(self, suite_parameter):
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        cycle = ok(create(owner, world, a), 201)
        job = ok(next_job(a))
        clock.tick(121)
        ok(a.heartbeat())
        [kept] = job_list(owner, cycle["id"])
        assert (kept["id"], kept["status"], kept["consumer_id"]) == (job["id"], "claimed", a.consumer["id"])

    @test()
    def test_overlapping_stall_checks_move_a_job_once(self, suite_parameter):
        app = self.env.app
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a, b = world["a"], world["b"]
        set_column(
            app, Consumer, "last_heartbeat_at", clock.now + timedelta(seconds=121), id=b.consumer["id"]
        )
        cycle = ok(create(owner, world, a), 201)
        job = ok(next_job(a))
        clock.tick(121)
        cutoff = clock.now - job_queue.STALL_AFTER
        with app.state.sessionmaker() as late:  # this check listed the job before the other one moved it
            org_id = late.get(Consumer, a.consumer["id"]).org_id
            assert job_queue.stalled_ids(late, org_id, cutoff) == [job["id"]]
            late.rollback()
            with app.state.sessionmaker() as first:
                assert job_queue.stall_check(first, org_id, clock.now) == 1
                first.commit()
            assert job_queue.take_stalled(late, job["id"], cutoff, clock.now) is None
        [requeued] = job_list(owner, cycle["id"])
        assert (requeued["status"], requeued["consumer_id"], requeued["attempts"]) == (
            "queued",
            b.consumer["id"],
            2,
        )

    # Long-poll

    @test()
    def test_long_poll_sees_a_job_queued_while_it_waits(self, suite_parameter):
        app = self.env.app
        owner = self.env.owner
        clock = make_clock(self.env)
        world = make_world(self.env, owner, clock)
        a = world["a"]
        cycle = ok(create(owner, world, mode="manual", consumer_ids=None), 201)
        with app.state.sessionmaker() as db:
            org_id = db.get(Consumer, a.consumer["id"]).org_id
        calls = []

        def sleep(_seconds):
            calls.append(1)
            if len(calls) == 1:  # queued from another session while jobs_next waits
                with app.state.sessionmaker() as db:
                    db.add(
                        Job(
                            org_id=org_id,
                            cycle_id=cycle["id"],
                            consumer_id=a.consumer["id"],
                            project="web",
                            refs=[REF_OK],
                            status="queued",
                        )
                    )
                    db.commit()

        self.env.patch(jobs, "_sleep", sleep)
        job = ok(next_job(a, wait=5))
        assert job["cycle_id"] == cycle["id"] and job["status"] == "claimed" and len(calls) == 1
        with app.state.sessionmaker() as db:
            assert db.scalar(select(Job.status).where(Job.id == job["id"])) == "claimed"

    @test(parameters=sorted(JOB_OPS))
    def test_job_operation_is_in_the_contract(self, suite_parameter, parameter):
        name = parameter
        spec = make_spec(self.env.client)
        scope, mcp = JOB_OPS[name]
        op = spec[name]
        assert (op.get("x-scope"), op["x-toolset"], op["x-mcp"]) == (scope, "execution", mcp)
