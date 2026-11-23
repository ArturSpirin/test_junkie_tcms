"""A cycle runs the case version it pinned; later case edits don't reach it (T4)."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import events, ok, url
from tests.execution_seed import cycle_cases, edit_steps, make_cycle, record, run_seed


@Suite(parameters=support.DATABASES)
class CyclePinning:
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
    def test_a_case_edit_does_not_change_a_cycle_already_created(self, suite_parameter):
        owner = self.env.owner
        s = run_seed(owner)
        v1_steps = s["cycle_case"]["steps"]
        edited = edit_steps(owner, s["case"])
        assert edited["current_version"] == 2

        [cc] = cycle_cases(owner, s["cycle"]["id"])
        assert (cc["case_version"], cc["current_version"]) == (1, 2)
        assert cc["steps"] == v1_steps
        assert cc["title"] == "Pay by card"

        # A cycle made after the edit pins version 2.
        later = make_cycle(owner, s["product"]["id"], case_ids=[s["case"]["id"]])
        [cc2] = cycle_cases(owner, later["id"])
        assert cc2["case_version"] == 2
        assert [st["id"] for st in cc2["steps"]] == [st["id"] for st in edited["steps"]]

    @test()
    def test_results_take_step_ids_of_the_pinned_version_only(self, suite_parameter):
        owner = self.env.owner
        s = run_seed(owner)
        v1_dropped = s["case"]["steps"][1]["id"]
        edited = edit_steps(owner, s["case"])
        v2_only = edited["steps"][1]["id"]
        assert v2_only not in {st["id"] for st in s["case"]["steps"]}

        cc = s["cycle_case"]["id"]
        refused = record(owner, cc, status="success", steps=[{"step_id": v2_only, "status": "success"}])
        assert refused.status_code == 422, refused.text
        # The step version 2 dropped is still a step of the pinned version 1.
        ok(record(owner, cc, status="fail", steps=[{"step_id": v1_dropped, "status": "fail"}]), 201)

    @test()
    def test_refresh_version_repins_without_results(self, suite_parameter):
        owner = self.env.owner
        s = run_seed(owner)
        edit_steps(owner, s["case"])
        cc = s["cycle_case"]["id"]
        refreshed = ok(owner.post(url(f"/cycle-cases/{cc}/refresh-version")))
        assert (refreshed["case_version"], refreshed["status"]) == (2, "untested")
        [event] = events(owner, "cycle_case")
        assert event["action"] == "cycle_case.refresh_version"
        assert event["changes"] == {"case_version": [1, 2]}

    @test()
    def test_refresh_version_after_results_reruns_on_the_new_version(self, suite_parameter):
        owner = self.env.owner
        s = run_seed(owner)
        cc = s["cycle_case"]["id"]
        ok(record(owner, cc, status="fail"), 201)
        ok(record(owner, cc, status="success"), 201)
        edited = edit_steps(owner, s["case"])

        refreshed = ok(owner.post(url(f"/cycle-cases/{cc}/refresh-version")))
        assert (refreshed["case_version"], refreshed["status"]) == (2, "untested")
        assert refreshed["last_result_at"] is not None
        [event] = events(owner, "cycle_case")
        assert event["changes"] == {"case_version": [1, 2], "status": ["success", "untested"]}
        # Nothing left to move: a second refresh changes nothing and records nothing.
        assert ok(owner.post(url(f"/cycle-cases/{cc}/refresh-version")))["case_version"] == 2
        assert len(events(owner, "cycle_case")) == 1

        # The rerun is attempt 3 on version 2, with version 2's step ids; the history stays.
        v2_only = edited["steps"][1]["id"]
        rerun = ok(
            record(owner, cc, status="success", steps=[{"step_id": v2_only, "status": "success"}]), 201
        )
        assert (rerun["attempt"], rerun["case_version"]) == (3, 2)
        history = ok(owner.get(url(f"/cycle-cases/{cc}/results")))["items"]
        assert [(r["attempt"], r["status"], r["case_version"]) for r in history] == [
            (1, "fail", 1),
            (2, "success", 1),
            (3, "success", 2),
        ]

    @test()
    def test_an_archived_case_keeps_its_place_in_an_existing_cycle(self, suite_parameter):
        owner = self.env.owner
        s = run_seed(owner)
        ok(owner.post(url(f"/cases/{s['case']['id']}/archive")))
        [cc] = cycle_cases(owner, s["cycle"]["id"])
        assert cc["case_version"] == 1
        ok(record(owner, cc["id"], status="success"), 201)
