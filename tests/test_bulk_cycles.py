"""Bulk cycles: pick a release, get one cycle per affected feature (or active plan) in one batch (T4)."""

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import events, make_feature, make_plan, make_release, ok, seed, url
from tests.execution_seed import activate, cycle_cases, make_case
from tests.support import add_member


def bulk(owner, release: str, status: int = 201, **body):
    response = owner.post(url(f"/releases/{release}/cycles/bulk"), json=body)
    assert response.status_code == status, response.text
    return response.json()


def keys(owner, cycle: dict) -> list[str]:
    return sorted(c["key"] for c in cycle_cases(owner, cycle["id"]))


@Suite(parameters=support.DATABASES)
class BulkCycles:
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
    def test_one_cycle_per_affected_feature_in_one_batch(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, parent, child = s["product"]["id"], s["parent"]["id"], s["child"]["id"]
        other = make_feature(owner, p, "Refunds")
        grandchild = make_feature(owner, p, "Saved cards", parent_id=child)
        make_case(owner, p, parent, "On the parent")  # PAY-1: parent is not affected, so no cycle runs it
        make_case(owner, p, child, "On the child")  # PAY-2
        make_case(owner, p, grandchild["id"], "Under the child")  # PAY-3: runs in the child's cycle
        make_case(owner, p, other["id"], "Refund")  # PAY-4
        make_case(owner, p, other["id"], "Archived")  # PAY-5
        ok(owner.post(url("/cases/PAY-5/archive")))
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [child, other["id"]]}))

        batch = bulk(owner, release, environment="staging")
        assert (batch["release_id"], batch["mode"], batch["name"]) == (release, "features", "1.0")
        by_feature = {c["feature_id"]: c for c in batch["cycles"]}
        assert set(by_feature) == {child, other["id"]}
        assert {c["batch_id"] for c in batch["cycles"]} == {batch["id"]}
        assert {c["release_id"] for c in batch["cycles"]} == {release}
        assert by_feature[child]["name"] == "1.0 · Card"
        assert keys(owner, by_feature[child]) == ["PAY-2", "PAY-3"]
        assert keys(owner, by_feature[other["id"]]) == ["PAY-4"]

        again = ok(owner.get(url(f"/cycle-batches/{batch['id']}")))
        assert {c["id"] for c in again["cycles"]} == {c["id"] for c in batch["cycles"]}
        [event] = events(owner, "cycle_batch")
        assert event["action"] == "cycle_batch.create"

    @test()
    def test_a_case_under_an_archived_sub_feature_runs_in_its_affected_ancestors_cycle(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, parent, child = s["product"]["id"], s["parent"]["id"], s["child"]["id"]
        make_case(owner, p, child, "Under the archived child")  # PAY-1
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [parent, child]}))
        ok(owner.post(url(f"/features/{child}/archive")))

        batch = bulk(owner, release)
        [cycle] = batch["cycles"]
        assert cycle["feature_id"] == parent  # the archived child gets no cycle of its own
        assert keys(owner, cycle) == ["PAY-1"]

    @test()
    def test_a_case_on_two_affected_levels_runs_once_in_the_nearest(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, parent, child = s["product"]["id"], s["parent"]["id"], s["child"]["id"]
        make_case(owner, p, child, "Child")  # PAY-1
        make_case(owner, p, parent, "Parent")  # PAY-2
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [parent, child]}))
        by_feature = {c["feature_id"]: c for c in bulk(owner, release)["cycles"]}
        assert keys(owner, by_feature[child]) == ["PAY-1"]
        assert keys(owner, by_feature[parent]) == ["PAY-2"]

    @test()
    def test_a_release_with_no_active_features_is_refused(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        release = make_release(owner, s["product"]["id"], "2.0")
        bulk(owner, release["id"], 422)
        assert ok(owner.get(url(f"/products/{s['product']['id']}/cycles")))["items"] == []

    @test()
    def test_plans_mode_makes_one_cycle_per_active_plan_of_the_release(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, child = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, child, "Card")  # PAY-1
        release = s["release"]["id"]
        draft = make_plan(owner, p, "Draft", release_id=release)
        bulk(owner, release, 422, mode="plans")  # only draft plans so far
        activate(owner, s["plan"]["id"])

        batch = bulk(owner, release, mode="plans", name="RC1")
        [cycle] = batch["cycles"]
        assert (cycle["plan_id"], cycle["name"]) == (s["plan"]["id"], "RC1 · Smoke")
        assert keys(owner, cycle) == ["PAY-1"]
        assert draft["id"] not in {c["plan_id"] for c in batch["cycles"]}

    @test()
    def test_a_listed_draft_plan_refuses_the_whole_batch(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, release = s["product"]["id"], s["release"]["id"]
        activate(owner, s["plan"]["id"])
        draft = make_plan(owner, p, "Draft", release_id=release)
        response = owner.post(
            url(f"/releases/{release}/cycles/bulk"),
            json={"mode": "plans", "plan_ids": [s["plan"]["id"], draft["id"]]},
        )
        assert response.status_code == 409 and response.json()["code"] == "plan_not_active"
        assert ok(owner.get(url(f"/products/{p}/cycles")))["items"] == []
        assert events(owner, "cycle_batch") == []
        bulk(owner, release, 422, mode="features", plan_ids=[s["plan"]["id"]])

    @test()
    def test_a_name_pattern_names_each_cycle_and_refuses_unknown_placeholders(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, child = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, child, "Card")
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [child]}))
        bad = owner.post(url(f"/releases/{release}/cycles/bulk"), json={"name_pattern": "{plan} on {env}"})
        assert bad.status_code == 422 and bad.json()["code"] == "bad_name_pattern"
        assert ok(owner.get(url(f"/products/{p}/cycles")))["items"] == []
        [cycle] = bulk(owner, release, name_pattern="{feature} {release} ({env})", environment="qa")["cycles"]
        assert cycle["name"] == "Card 1.0 (qa)"

    @test()
    def test_assignees_set_each_cycles_default_assignee(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, child = s["product"]["id"], s["child"]["id"]
        other = make_feature(owner, p, "Refunds")
        make_case(owner, p, child, "Card")
        make_case(owner, p, other["id"], "Refund")
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [child, other["id"]]}))
        tess = add_member(owner, "tess@example.com", "tester")["actor_id"]
        bulk(owner, release, 422, assignees={child: "nobody"})
        bulk(owner, release, 422, assignees={s["parent"]["id"]: tess})  # not a feature of this batch
        by_feature = {c["feature_id"]: c for c in bulk(owner, release, assignees={child: tess})["cycles"]}
        assert by_feature[child]["default_assignee_actor_id"] == tess
        assert by_feature[other["id"]]["default_assignee_actor_id"] is None

    @test()
    def test_skip_drafts_leaves_draft_cases_out_and_counts_them(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, child = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, child, "Draft")  # PAY-1
        make_case(owner, p, child, "Ready", status="ready")  # PAY-2
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [child]}))
        [kept] = bulk(owner, release)["cycles"]
        assert keys(owner, kept) == ["PAY-1", "PAY-2"]
        [cycle] = bulk(owner, release, skip_drafts=True)["cycles"]
        assert keys(owner, cycle) == ["PAY-2"]
        assert cycle["skipped"] == {"archived": 0, "deprecated": 0, "draft": 1}

    @test()
    def test_a_released_release_gets_no_new_cycles(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, child = s["product"]["id"], s["child"]["id"]
        case = make_case(owner, p, child, "Card")
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [child]}))
        ok(owner.patch(url(f"/releases/{release}"), json={"status": "released"}))
        refused = owner.post(url(f"/releases/{release}/cycles/bulk"), json={})
        assert refused.status_code == 409 and refused.json()["code"] == "release_closed"
        one = owner.post(
            url(f"/products/{p}/cycles"), json={"name": "R", "release_id": release, "case_ids": [case["id"]]}
        )
        assert one.status_code == 409 and one.json()["code"] == "release_closed"
        assert ok(owner.get(url(f"/products/{p}/cycles")))["items"] == []

    @test()
    def test_a_batch_is_closed_by_whoever_closes_its_last_cycle(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, child = s["product"]["id"], s["child"]["id"]
        other = make_feature(owner, p, "Refunds")
        make_case(owner, p, child, "Card")
        make_case(owner, p, other["id"], "Refund")
        release = s["release"]["id"]
        ok(owner.put(url(f"/releases/{release}/features"), json={"feature_ids": [child, other["id"]]}))
        batch = bulk(owner, release)
        assert batch["created_by_actor_id"] and batch["closed_by_actor_id"] is None
        first, second = batch["cycles"]
        ok(owner.post(url(f"/cycles/{first['id']}/close")))
        half = ok(owner.get(url(f"/cycle-batches/{batch['id']}")))
        assert (half["closed_at"], half["closed_by_actor_id"]) == (None, None)
        last = ok(owner.post(url(f"/cycles/{second['id']}/close")))
        done = ok(owner.get(url(f"/cycle-batches/{batch['id']}")))
        assert done["closed_at"] == last["closed_at"]
        assert done["closed_by_actor_id"] == batch["created_by_actor_id"]
