"""T6 CSV: export, import into another product, round trip, and all-or-nothing import errors."""

import csv
import io
import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import events, make_product, ok, seed, url
from tests.execution_seed import STEPS, make_case


def export(client, product: str, **body) -> str:
    r = client.post(url(f"/products/{product}/exports"), json={"format": "csv", **body})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    return r.text


def rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def to_csv(items: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(items[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(items)
    return out.getvalue()


def do_import(client, product: str, text: str, **body):
    return client.post(url(f"/products/{product}/imports"), json={"csv": text, **body})


def comparable(row: dict) -> dict:
    """A row without what differs between products: the key, the version and the step ids."""
    steps = [{k: v for k, v in s.items() if k != "id"} for s in json.loads(row["steps"])]
    return {**{k: v for k, v in row.items() if k not in ("key", "version")}, "steps": steps}


def source(owner) -> dict:
    s = seed(owner, "PAY")
    p, f = s["product"]["id"], s["child"]["id"]
    make_case(
        owner,
        p,
        f,
        "Pay by card",
        preconditions={"markdown": "A **saved** card, and a cart with:\n\n- one item\n- a coupon"},
        steps=STEPS,
        tags=["smoke", "payments"],
        links=[{"url": "https://example.com/BUG-7", "key": "BUG-7"}],
        automation_ref="tests/test_pay.py::test_card",
    )
    make_case(owner, p, s["parent"]["id"], 'Checkout, with a comma and "quotes"', priority="high")
    return s


def cases_count(owner, product: str) -> int:
    return len(ok(owner.get(url(f"/products/{product}/cases"), params={"limit": 200}))["items"])


@Suite(parameters=support.DATABASES)
class CsvIo:
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
    def test_export_has_the_import_columns(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        out = rows(export(owner, s["product"]["id"]))
        assert [r["key"] for r in out] == ["PAY-1", "PAY-2"]
        first = out[0]
        assert (first["version"], first["feature"], first["title"]) == ("1", "Checkout > Card", "Pay by card")
        assert json.loads(first["tags"]) == ["payments", "smoke"]
        assert json.loads(first["links"]) == [{"url": "https://example.com/BUG-7", "key": "BUG-7"}]
        assert [s["action"] for s in json.loads(first["steps"])] == ["Open the cart", "Pay by card"]

    @test()
    def test_export_of_a_feature_subtree(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        out = rows(export(owner, s["product"]["id"], feature=s["child"]["id"]))
        assert [r["key"] for r in out] == ["PAY-1"]

    @test()
    def test_round_trip_into_another_product(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        first = export(owner, s["product"]["id"])
        target = make_product(owner, "NEW")
        fresh = [{**r, "key": "", "version": ""} for r in rows(first)]
        out = ok(do_import(owner, target["id"], to_csv(fresh), create_features=True))
        assert (out["created"], out["updated"], out["unchanged"], out["keys"]) == (
            2,
            0,
            0,
            ["NEW-1", "NEW-2"],
        )
        second = export(owner, target["id"])
        assert [comparable(r) for r in rows(second)] == [comparable(r) for r in rows(first)]
        again = ok(do_import(owner, target["id"], second))
        assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 2)
        assert export(owner, target["id"]) == second  # no new versions
        summary = [e for e in events(owner, "product") if e["action"] == "cases.import"]
        assert len(summary) == 2

    @test()
    def test_import_edits_a_case_at_its_version(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        items = rows(export(owner, s["product"]["id"]))
        items[0]["title"] = "Pay by saved card"
        out = ok(do_import(owner, s["product"]["id"], to_csv(items)))
        assert (out["created"], out["updated"], out["unchanged"]) == (0, 1, 1)
        case = ok(owner.get(url("/cases/PAY-1")))
        assert (case["title"], case["current_version"]) == ("Pay by saved card", 2)

    @test()
    def test_export_has_the_description_and_an_old_header_keeps_it(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        ok(
            owner.patch(
                url("/cases/PAY-1"),
                json={"description": {"markdown": "Card payments"}},
                headers={"If-Match": '"1"'},
            )
        )
        items = rows(export(owner, s["product"]["id"]))
        assert items[0]["description"].strip() == "Card payments"
        old = [{k: v for k, v in r.items() if k != "description"} for r in items]
        old[0]["title"] = "Pay by saved card"
        out = ok(do_import(owner, s["product"]["id"], to_csv(old)))
        assert (out["created"], out["updated"], out["unchanged"]) == (0, 1, 1)
        case = ok(owner.get(url("/cases/PAY-1")))
        assert (case["title"], case["description"].strip()) == ("Pay by saved card", "Card payments")

    @test()
    def test_version_mismatch_rejects_the_whole_import(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        items = rows(export(owner, s["product"]["id"]))
        ok(owner.patch(url("/cases/PAY-1"), json={"title": "Edited since"}, headers={"If-Match": '"1"'}))
        items[0]["title"] = "Stale edit"
        items[1]["title"] = "Fine edit"
        items.append({**items[1], "key": "", "version": "", "title": "Brand new"})
        r = do_import(owner, s["product"]["id"], to_csv(items))
        assert r.status_code == 422, r.text
        assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(1, "version")]
        assert ok(owner.get(url("/cases/PAY-1")))["title"] == "Edited since"
        assert ok(owner.get(url("/cases/PAY-2")))["current_version"] == 1
        assert cases_count(owner, s["product"]["id"]) == 2

    @test()
    def test_blank_version_on_a_keyed_row_is_a_row_error(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        items = rows(export(owner, s["product"]["id"]))
        items[1]["version"] = ""
        r = do_import(owner, s["product"]["id"], to_csv(items))
        assert r.status_code == 422, r.text
        assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(2, "version")]

    @test()
    def test_feature_change_on_a_keyed_row_is_a_row_error(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        items = rows(export(owner, s["product"]["id"]))
        items[0]["feature"] = "Checkout"
        r = do_import(owner, s["product"]["id"], to_csv(items))
        assert r.status_code == 422, r.text
        assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(1, "feature")]

    @test()
    def test_missing_feature_needs_create_features(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        items = [
            {**r, "key": "", "version": "", "feature": "Somewhere > New"}
            for r in rows(export(owner, s["product"]["id"]))
        ]
        r = do_import(owner, s["product"]["id"], to_csv(items))
        assert r.status_code == 422, r.text
        assert {e["column"] for e in r.json()["errors"]} == {"feature"}
        assert cases_count(owner, s["product"]["id"]) == 2

    @test()
    def test_duplicate_key_is_a_row_error(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        items = rows(export(owner, s["product"]["id"]))
        r = do_import(owner, s["product"]["id"], to_csv(items + [items[0]]))
        assert r.status_code == 422, r.text
        assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(3, "key")]

    @test()
    def test_dry_run_writes_nothing(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        target = make_product(owner, "NEW")
        fresh = [{**r, "key": "", "version": ""} for r in rows(export(owner, s["product"]["id"]))]
        out = ok(do_import(owner, target["id"], to_csv(fresh), create_features=True, dry_run=True))
        assert (out["created"], out["dry_run"]) == (2, True)
        assert cases_count(owner, target["id"]) == 0
        assert ok(owner.get(url(f"/products/{target['id']}/features")))["items"] == []

    @test()
    def test_refused_requests(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        text = export(owner, p)
        assert do_import(owner, p, text, mapping={"Title": "title"}).status_code == 422
        assert do_import(owner, p, "title,steps\nx,[]\n").status_code == 422
        assert do_import(owner, p, text.splitlines()[0] + "\n").status_code == 422
        assert do_import(owner, p, "x" * (5 * 1024 * 1024 + 1)).status_code == 413
        bundle = owner.post(url(f"/products/{p}/exports"), json={"format": "md-bundle"})
        assert (bundle.status_code, bundle.headers["content-type"]) == (200, "application/zip")
        assert do_import(owner, p, text, bundle="").status_code == 422
        assert owner.post(url(f"/products/{p}/imports"), json={}).status_code == 422

    @test()
    def test_mapping_imports_a_foreign_csv(self, suite_parameter):
        owner = self.env.owner
        target = make_product(owner, "NEW")
        out = ok(do_import(owner, target["id"], FOREIGN, mapping=MAPPING, create_features=True))
        assert (out["created"], out["keys"]) == (2, ["NEW-1", "NEW-2"])
        got = rows(export(owner, target["id"]))
        first = got[0]
        assert (first["feature"], first["title"], first["priority"]) == (
            "Checkout > Card",
            "Pay by card",
            "high",
        )
        assert json.loads(first["tags"]) == ["payments", "smoke"]
        assert [(s["action"], s["expected"]) for s in json.loads(first["steps"])] == [
            ("Open the cart", "The total shows")
        ]
        second = got[1]
        assert (second["title"], json.loads(second["steps"]), json.loads(second["tags"])) == (
            "Refund",
            [],
            [],
        )
        assert second["priority"] == "medium"  # blank means the case default

    @test()
    def test_mapping_with_our_column_names_needs_no_entry(self, suite_parameter):
        owner = self.env.owner
        target = make_product(owner, "NEW")
        text = "title,Section\nPlain,Checkout\n"
        out = ok(do_import(owner, target["id"], text, mapping={"Section": "feature"}, create_features=True))
        assert out["created"] == 1

    @test()
    def test_bad_mappings_write_nothing(self, suite_parameter):
        owner = self.env.owner
        target = make_product(owner, "NEW")
        bad = [
            ({**MAPPING, "Titel": "title"}, "doesn't have"),
            ({**MAPPING, "Priority": "urgency"}, "urgency"),
            ({**MAPPING, "Labels": "title"}, "More than one column maps to: title"),
            ({k: v for k, v in MAPPING.items() if k != "Notes"}, "Notes"),
            ({**MAPPING, "Title": None}, "Nothing maps to title"),
            ({**MAPPING, "Labels": "steps"}, "steps can't be used"),
        ]
        for mapping, detail in bad:
            r = do_import(owner, target["id"], FOREIGN, mapping=mapping, create_features=True)
            assert r.status_code == 422, (mapping, r.text)
            assert detail in r.json()["detail"], (detail, r.text)
        assert cases_count(owner, target["id"]) == 0
        assert ok(owner.get(url(f"/products/{target['id']}/features")))["items"] == []

    @test()
    def test_mapped_row_error_names_the_callers_column(self, suite_parameter):
        owner = self.env.owner
        target = make_product(owner, "NEW")
        text = FOREIGN.replace(",high,", ",urgent,")
        r = do_import(owner, target["id"], text, mapping=MAPPING, create_features=True)
        assert r.status_code == 422, r.text
        assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(1, "Priority")]
        assert cases_count(owner, target["id"]) == 0

    @test()
    def test_mapped_key_and_version_edit_a_case(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        mapping = {"ID": "key", "Rev": "version", "Section": "feature", "Name": "title"}
        out = ok(do_import(owner, p, "ID,Rev,Section,Name\nPAY-2,1,Checkout,Renamed\n", mapping=mapping))
        assert (out["created"], out["updated"]) == (0, 1)
        case = ok(owner.get(url("/cases/PAY-2")))
        assert (case["title"], case["current_version"]) == ("Renamed", 2)
        r = do_import(owner, p, "ID,Rev,Section,Name\nPAY-2,1,Checkout,Stale\n", mapping=mapping)
        assert r.status_code == 422, r.text
        assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(1, "Rev")]
        assert ok(owner.get(url("/cases/PAY-2")))["title"] == "Renamed"

    @test()
    def test_mapped_edit_keeps_the_columns_it_doesnt_map(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        before = rows(export(owner, p))[0]
        mapping = {"ID": "key", "Rev": "version", "Section": "feature", "Name": "title"}
        text = "ID,Rev,Section,Name\nPAY-1,1,Checkout > Card,Pay by saved card\n"
        out = ok(do_import(owner, p, text, mapping=mapping))
        assert (out["created"], out["updated"]) == (0, 1)
        keep = ("feature", "preconditions", "steps", "automation_ref", "tags", "links", "custom")
        edited = rows(export(owner, p))[0]
        assert {c: edited[c] for c in keep} == {c: before[c] for c in keep}
        text = "ID,Rev,Name\nPAY-1,2,Pay by stored card\n"
        out = ok(do_import(owner, p, text, mapping={"ID": "key", "Rev": "version", "Name": "title"}))
        assert (out["created"], out["updated"]) == (0, 1)
        after = rows(export(owner, p))[0]
        assert (after["title"], after["version"]) == ("Pay by stored card", "3")
        assert {c: after[c] for c in keep} == {c: before[c] for c in keep}
        assert len(json.loads(after["steps"])) == 2


FOREIGN = (
    "Title,Section,Steps,Expected Result,Labels,Priority,Notes\n"
    'Pay by card,Checkout > Card,Open the cart,The total shows,"smoke, payments",high,ignore me\n'
    "Refund,Checkout,,,,,\n"
)
MAPPING = {
    "Title": "title",
    "Section": "feature",
    "Steps": "step_action",
    "Expected Result": "step_expected",
    "Labels": "tags",
    "Priority": "priority",
    "Notes": None,
}
