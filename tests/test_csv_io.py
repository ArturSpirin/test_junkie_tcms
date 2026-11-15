"""T6 CSV: export, import into another product, round trip, and all-or-nothing import errors."""

import csv
import io
import json

from catalog_seed import events, make_product, ok, seed, url
from execution_seed import STEPS, make_case


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


def test_export_has_the_import_columns(owner):
    s = source(owner)
    out = rows(export(owner, s["product"]["id"]))
    assert [r["key"] for r in out] == ["PAY-1", "PAY-2"]
    first = out[0]
    assert (first["version"], first["feature"], first["title"]) == ("1", "Checkout > Card", "Pay by card")
    assert json.loads(first["tags"]) == ["payments", "smoke"]
    assert json.loads(first["links"]) == [{"url": "https://example.com/BUG-7", "key": "BUG-7"}]
    assert [s["action"] for s in json.loads(first["steps"])] == ["Open the cart", "Pay by card"]


def test_export_of_a_feature_subtree(owner):
    s = source(owner)
    out = rows(export(owner, s["product"]["id"], feature=s["child"]["id"]))
    assert [r["key"] for r in out] == ["PAY-1"]


def test_round_trip_into_another_product(owner):
    s = source(owner)
    first = export(owner, s["product"]["id"])
    target = make_product(owner, "NEW")
    fresh = [{**r, "key": "", "version": ""} for r in rows(first)]
    out = ok(do_import(owner, target["id"], to_csv(fresh), create_features=True))
    assert (out["created"], out["updated"], out["unchanged"], out["keys"]) == (2, 0, 0, ["NEW-1", "NEW-2"])
    second = export(owner, target["id"])
    assert [comparable(r) for r in rows(second)] == [comparable(r) for r in rows(first)]
    again = ok(do_import(owner, target["id"], second))
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 2)
    assert export(owner, target["id"]) == second  # no new versions
    summary = [e for e in events(owner, "product") if e["action"] == "cases.import"]
    assert len(summary) == 2


def test_import_edits_a_case_at_its_version(owner):
    s = source(owner)
    items = rows(export(owner, s["product"]["id"]))
    items[0]["title"] = "Pay by saved card"
    out = ok(do_import(owner, s["product"]["id"], to_csv(items)))
    assert (out["created"], out["updated"], out["unchanged"]) == (0, 1, 1)
    case = ok(owner.get(url("/cases/PAY-1")))
    assert (case["title"], case["current_version"]) == ("Pay by saved card", 2)


def test_version_mismatch_rejects_the_whole_import(owner):
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


def test_blank_version_on_a_keyed_row_is_a_row_error(owner):
    s = source(owner)
    items = rows(export(owner, s["product"]["id"]))
    items[1]["version"] = ""
    r = do_import(owner, s["product"]["id"], to_csv(items))
    assert r.status_code == 422, r.text
    assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(2, "version")]


def test_feature_change_on_a_keyed_row_is_a_row_error(owner):
    s = source(owner)
    items = rows(export(owner, s["product"]["id"]))
    items[0]["feature"] = "Checkout"
    r = do_import(owner, s["product"]["id"], to_csv(items))
    assert r.status_code == 422, r.text
    assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(1, "feature")]


def test_missing_feature_needs_create_features(owner):
    s = source(owner)
    items = [
        {**r, "key": "", "version": "", "feature": "Somewhere > New"}
        for r in rows(export(owner, s["product"]["id"]))
    ]
    r = do_import(owner, s["product"]["id"], to_csv(items))
    assert r.status_code == 422, r.text
    assert {e["column"] for e in r.json()["errors"]} == {"feature"}
    assert cases_count(owner, s["product"]["id"]) == 2


def test_duplicate_key_is_a_row_error(owner):
    s = source(owner)
    items = rows(export(owner, s["product"]["id"]))
    r = do_import(owner, s["product"]["id"], to_csv(items + [items[0]]))
    assert r.status_code == 422, r.text
    assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(3, "key")]


def test_dry_run_writes_nothing(owner):
    s = source(owner)
    target = make_product(owner, "NEW")
    fresh = [{**r, "key": "", "version": ""} for r in rows(export(owner, s["product"]["id"]))]
    out = ok(do_import(owner, target["id"], to_csv(fresh), create_features=True, dry_run=True))
    assert (out["created"], out["dry_run"]) == (2, True)
    assert cases_count(owner, target["id"]) == 0
    assert ok(owner.get(url(f"/products/{target['id']}/features")))["items"] == []


def test_refused_requests(owner):
    s = source(owner)
    p = s["product"]["id"]
    text = export(owner, p)
    assert do_import(owner, p, text, mapping={"Title": "title"}).status_code == 422
    assert do_import(owner, p, "title,steps\nx,[]\n").status_code == 422
    assert do_import(owner, p, text.splitlines()[0] + "\n").status_code == 422
    assert do_import(owner, p, "x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert owner.post(url(f"/products/{p}/exports"), json={"format": "md-bundle"}).status_code == 422
