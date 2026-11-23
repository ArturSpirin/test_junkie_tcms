"""Starting a cycle with an ETA and a run order: by feature, by priority, or a manual case order."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.models import Cycle
from tests import support
from tests.catalog_seed import events, make_feature, make_product, ok, url
from tests.execution_seed import cycle_cases, make_case, make_cycle


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def start(owner, product: str, **body) -> dict:
    return make_cycle(owner, product, product_id=product, **body)


def run_keys(owner, cycle: str) -> list[str]:
    return [cc["key"] for cc in cycle_cases(owner, cycle, sort="position", limit=200)]


@Suite(parameters=support.DATABASES)
class CycleEtaOrder:
    @beforeTest()
    def open_env(self, suite_parameter):
        self.env = support.Env(suite_parameter)

    @afterTest()
    def close_env(self):
        self.env.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def catalog(self):
        """Two top features, B before A in the tree; cases PAY-1..4 made out of tree order, mixed priority."""
        owner = self.env.owner
        p = make_product(owner)["id"]
        b = make_feature(owner, p, "B")["id"]
        a = make_feature(owner, p, "A")["id"]
        make_case(owner, p, a, "a low", priority="low")
        make_case(owner, p, b, "b high", priority="high")
        make_case(owner, p, a, "a critical", priority="critical")
        make_case(owner, p, b, "b medium", priority="medium")
        return owner, p

    @test()
    def test_eta_reads_back_and_a_past_eta_is_a_422(self, suite_parameter):
        owner, p = self.catalog()
        eta = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
        cycle = start(owner, p, eta=iso(eta))
        assert datetime.fromisoformat(cycle["eta"]) == eta
        assert datetime.fromisoformat(ok(owner.get(url(f"/cycles/{cycle['id']}")))["eta"]) == eta
        assert ok(owner.get(url(f"/products/{p}/cycles")))["items"][0]["eta"] == cycle["eta"]
        [event] = events(owner, "cycle")
        assert event["changes"]["eta"][1] is not None
        past = iso(datetime.now(UTC) - timedelta(hours=1))
        response = owner.post(url(f"/products/{p}/cycles"), json={"name": "R", "eta": past})
        assert (response.status_code, response.json()["code"]) == (422, "eta_in_past"), response.text
        response = owner.patch(url(f"/cycles/{cycle['id']}"), json={"eta": past})
        assert (response.status_code, response.json()["code"]) == (422, "eta_in_past"), response.text
        assert ok(owner.patch(url(f"/cycles/{cycle['id']}"), json={"eta": None}))["eta"] is None

    @test()
    def test_an_update_that_leaves_a_passed_eta_alone_still_works(self, suite_parameter):
        owner, p = self.catalog()
        eta = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0)
        cycle = start(owner, p, eta=iso(eta))
        passed = datetime.now(UTC) - timedelta(days=1)
        with self.env.app.state.sessionmaker() as db:
            db.scalar(select(Cycle).where(Cycle.id == cycle["id"])).eta = passed
            db.commit()
        same = ok(owner.get(url(f"/cycles/{cycle['id']}")))["eta"]
        assert ok(owner.patch(url(f"/cycles/{cycle['id']}"), json={"name": "Renamed"}))["name"] == "Renamed"
        assert ok(owner.patch(url(f"/cycles/{cycle['id']}"), json={"eta": same}))["eta"] == same

    @test()
    def test_order_by_feature_walks_the_tree(self, suite_parameter):
        owner, p = self.catalog()
        cycle = start(owner, p, order="feature")
        assert cycle["order"] == "feature"
        assert run_keys(owner, cycle["id"]) == ["PAY-2", "PAY-4", "PAY-1", "PAY-3"]

    @test()
    def test_order_by_priority_puts_critical_first(self, suite_parameter):
        owner, p = self.catalog()
        cycle = start(owner, p, order="priority")
        assert cycle["order"] == "priority"
        assert run_keys(owner, cycle["id"]) == ["PAY-3", "PAY-2", "PAY-4", "PAY-1"]

    @test()
    def test_the_default_order_is_the_source_and_reads_back(self, suite_parameter):
        owner, p = self.catalog()
        cycle = start(owner, p)
        assert ok(owner.get(url(f"/cycles/{cycle['id']}")))["order"] == "source"

    @test()
    def test_a_manual_case_order_runs_first_and_is_stored_as_manual(self, suite_parameter):
        owner, p = self.catalog()
        cycle = start(owner, p, order="priority", case_order=["PAY-4", "PAY-1"])
        assert cycle["order"] == "manual"
        assert ok(owner.get(url(f"/cycles/{cycle['id']}")))["order"] == "manual"
        assert run_keys(owner, cycle["id"]) == ["PAY-4", "PAY-1", "PAY-3", "PAY-2"]
        by_id = [cc["key"] for cc in cycle_cases(owner, cycle["id"])]
        assert sorted(by_id) == ["PAY-1", "PAY-2", "PAY-3", "PAY-4"]

    @test()
    def test_a_case_order_naming_a_case_the_run_skips_is_a_422(self, suite_parameter):
        owner, p = self.catalog()
        ok(owner.post(url("/cases/PAY-2/archive")))
        cycles = url(f"/products/{p}/cycles")
        response = owner.post(cycles, json={"name": "R", "product_id": p, "case_order": ["PAY-1", "PAY-2"]})
        assert (response.status_code, response.json()["code"]) == (422, "case_not_in_run"), response.text
        response = owner.post(cycles, json={"name": "R", "product_id": p, "case_order": ["PAY-99"]})
        assert response.status_code == 422, response.text

    @test()
    def test_a_request_cannot_ask_for_manual_order(self, suite_parameter):
        owner, p = self.catalog()
        response = owner.post(url(f"/products/{p}/cycles"), json={"name": "R", "order": "manual"})
        assert response.status_code == 422, response.text
        assert ok(owner.get(url(f"/products/{p}/cycles")))["total"] == 0
