"""Test cases: every content edit adds an immutable version, read back as history or one version (T3)."""

from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.models import CaseVersion, CaseVersionTag, Tag, TestCase
from test_junkie_tcms.db.session import CaseVersionImmutableError
from tests import support
from tests.catalog_seed import events, make_feature, make_product, ok, seed, url
from tests.execution_seed import cycle_cases, make_cycle, record
from tests.support import add_member


def make_case(
    client, product: str, feature: str, title: str = "Pay by card", org: str = "acme", **body
) -> dict:
    return ok(
        client.post(
            url(f"/products/{product}/cases", org), json={"feature_id": feature, "title": title, **body}
        ),
        201,
    )


def patch(client, case: str, version: int, body: dict, org: str = "acme"):
    return client.patch(url(f"/cases/{case}", org), json=body, headers={"If-Match": f'"{version}"'})


STEPS = [
    {"action": {"markdown": "Open checkout"}, "expected": {"markdown": "The form shows"}},
    {"action": {"markdown": "Pay"}},
]


@Suite(parameters=support.DATABASES)
class Cases:
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
    def test_create_numbers_cases_and_starts_at_version_1(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, f = s["product"]["id"], s["child"]["id"]
        response = owner.post(
            url(f"/products/{p}/cases"), json={"feature_id": f, "title": "Pay", "steps": STEPS}
        )
        case = ok(response, 201)
        assert response.headers["ETag"] == '"1"'
        assert response.headers["Location"] == f"/api/v1/orgs/acme/cases/{case['id']}"
        assert (case["key"], case["number"], case["current_version"]) == ("PAY-1", 1, 1)
        assert (case["priority"], case["type"], case["status"], case["automation"]) == (
            "medium",
            "functional",
            "draft",
            "manual",
        )
        assert [st["action"].strip() for st in case["steps"]] == [
            "Open checkout",
            "Pay",
        ]  # Markdown by default
        assert case["steps"][1]["expected"].strip() == ""
        assert make_case(owner, p, f)["key"] == "PAY-2"
        assert ok(owner.get(url("/cases/PAY-1")))["id"] == case["id"]
        assert [e["action"] for e in events(owner, "test_case")] == ["case.create", "case.create"]

    @test()
    def test_every_edit_adds_a_version_and_history_reads_back(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        case = make_case(owner, s["product"]["id"], s["child"]["id"], steps=STEPS)
        r = patch(owner, "PAY-1", 1, {"title": "Pay by card v2", "change_note": "rename"})
        assert ok(r)["current_version"] == 2
        assert r.headers["ETag"] == '"2"'
        assert (
            ok(patch(owner, "PAY-1", 2, {"status": "ready"}))["current_version"] == 3
        )  # status edits version too
        history = ok(owner.get(url("/cases/PAY-1/versions")))
        assert [(v["version"], v["title"], v["change_note"]) for v in history["items"]] == [
            (3, "Pay by card v2", None),
            (2, "Pay by card v2", "rename"),
            (1, "Pay by card", None),
        ]
        page = ok(owner.get(url("/cases/PAY-1/versions"), params={"limit": 2}))
        assert page["next_cursor"] == "2"
        rest = ok(owner.get(url("/cases/PAY-1/versions"), params={"limit": 2, "cursor": page["next_cursor"]}))
        assert [v["version"] for v in rest["items"]] == [1]
        v1 = ok(owner.get(url(f"/cases/{case['id']}/versions/1")))
        assert (v1["title"], v1["status"], v1["key"]) == ("Pay by card", "draft", "PAY-1")
        assert owner.get(url("/cases/PAY-1/versions/9")).status_code == 404
        updates = [
            e["changes"]["entity_version"] for e in events(owner, "test_case") if e["action"] == "case.update"
        ]
        assert sorted(updates) == [[1, 2], [2, 3]]

    @test()
    def test_same_content_adds_no_version(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        make_case(owner, s["product"]["id"], s["child"]["id"])
        assert ok(patch(owner, "PAY-1", 1, {"title": "Pay by card"}))["current_version"] == 1
        assert len(ok(owner.get(url("/cases/PAY-1/versions")))["items"]) == 1

    @test()
    def test_steps_reorder_keeps_their_ids(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        case = make_case(owner, s["product"]["id"], s["child"]["id"], steps=STEPS)
        first, second = case["steps"]
        body = {
            "steps": [{"id": second["id"], "action": {"markdown": "Pay"}}, {"id": first["id"], **STEPS[0]}]
        }
        moved = ok(patch(owner, "PAY-1", 1, body))
        assert [st["id"] for st in moved["steps"]] == [second["id"], first["id"]]
        v1 = ok(owner.get(url("/cases/PAY-1/versions/1")))
        assert [st["id"] for st in v1["steps"]] == [first["id"], second["id"]]  # the old version is untouched
        bad = patch(owner, "PAY-1", 2, {"steps": [{"id": "nope", "action": {"markdown": "x"}}]})
        assert bad.status_code == 422

    @test()
    def test_tags_live_on_versions_through_the_join_table(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        app = self.env.app
        p = s["product"]["id"]
        make_case(owner, p, s["child"]["id"], tags=["Smoke", "pay"])
        ok(patch(owner, "PAY-1", 1, {"tags": ["regression"]}))
        assert ok(owner.get(url("/cases/PAY-1")))["tags"] == ["regression"]
        assert ok(owner.get(url("/cases/PAY-1/versions/1")))["tags"] == ["pay", "smoke"]
        tags = ok(owner.get(url(f"/products/{p}/tags")))["items"]
        assert [(t["name"], t["case_count"]) for t in tags] == [("pay", 0), ("regression", 1), ("smoke", 0)]
        assert [
            c["key"]
            for c in ok(owner.get(url(f"/products/{p}/cases"), params={"tag": "regression"}))["items"]
        ] == ["PAY-1"]
        assert patch(owner, "PAY-1", 2, {"tags": ["Bad tag"]}).status_code == 422
        # A tag with the same name in another product is another row: the tag's product is always the case's.
        other = make_product(owner, "SHOP")
        make_case(owner, other["id"], make_feature(owner, other["id"], "Cart")["id"], tags=["smoke"])
        with app.state.sessionmaker() as db:
            rows = db.execute(
                select(TestCase.product_id, Tag.product_id)
                .select_from(CaseVersionTag)
                .join(Tag, Tag.id == CaseVersionTag.tag_id)
                .join(CaseVersion, CaseVersion.id == CaseVersionTag.case_version_id)
                .join(TestCase, TestCase.id == CaseVersion.case_id)
            ).all()
        assert len(rows) == 4
        assert all(case_product == tag_product for case_product, tag_product in rows)

    @test()
    def test_restore_copies_an_old_version_forward(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        make_case(owner, s["product"]["id"], s["child"]["id"])
        ok(patch(owner, "PAY-1", 1, {"title": "Renamed"}))
        r = owner.post(url("/cases/PAY-1/restore"), json={"version": 1}, headers={"If-Match": "2"})
        restored = ok(r)
        assert (restored["current_version"], restored["title"], restored["change_note"]) == (
            3,
            "Pay by card",
            "Restored version 1",
        )
        assert (
            owner.post(
                url("/cases/PAY-1/restore"), json={"version": 1}, headers={"If-Match": "2"}
            ).status_code
            == 409
        )

    @test()
    def test_move_and_archive_add_no_version(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        make_case(owner, s["product"]["id"], s["child"]["id"])
        moved = ok(owner.post(url("/cases/PAY-1/move"), json={"feature_id": s["parent"]["id"]}))
        assert (moved["feature_id"], moved["current_version"]) == (s["parent"]["id"], 1)
        p = s["product"]["id"]
        listed = ok(owner.get(url(f"/products/{p}/cases"), params={"feature": s["parent"]["id"]}))["items"]
        assert [c["key"] for c in listed] == ["PAY-1"]
        archived = ok(owner.post(url("/cases/PAY-1/archive")))
        assert archived["archived_at"] is not None and archived["current_version"] == 1
        assert ok(owner.get(url(f"/products/{p}/cases")))["items"] == []
        assert (
            len(ok(owner.get(url(f"/products/{p}/cases"), params={"include_archived": True}))["items"]) == 1
        )
        assert patch(owner, "PAY-1", 1, {"title": "x"}).status_code == 409

    @test()
    def test_bulk_upsert_is_all_or_nothing(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, f = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, f)
        body = {
            "items": [
                {"feature_id": f, "title": "New one"},
                {"key": "PAY-1", "expected_version": 1, "title": "Edited"},
                {"key": "PAY-1", "expected_version": 2, "title": "Edited"},
            ]
        }
        out = ok(owner.post(url(f"/products/{p}/cases/bulk"), json=body))["items"]
        assert [(i["key"], i["version"], i["result"]) for i in out] == [
            ("PAY-2", 1, "created"),
            ("PAY-1", 2, "updated"),
            ("PAY-1", 2, "unchanged"),
        ]
        stale = {
            "items": [
                {"feature_id": f, "title": "Never"},
                {"key": "PAY-1", "expected_version": 1, "title": "x"},
            ]
        }
        r = owner.post(url(f"/products/{p}/cases/bulk"), json=stale)
        assert r.status_code == 409 and r.json()["current_version"] == 2
        assert [c["key"] for c in ok(owner.get(url(f"/products/{p}/cases")))["items"]] == ["PAY-1", "PAY-2"]

    @test()
    def test_a_title_of_only_spaces_is_a_422_on_every_write(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, f = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, f)
        for title in ("", "   ", "\t \n"):
            created = owner.post(url(f"/products/{p}/cases"), json={"feature_id": f, "title": title})
            assert created.status_code == 422, (title, created.text)
            assert patch(owner, "PAY-1", 1, {"title": title}).status_code == 422, title
            edit = {"key": "PAY-1", "expected_version": 1, "title": title}
            for item in ({"feature_id": f, "title": title}, edit):
                bulk = owner.post(url(f"/products/{p}/cases/bulk"), json={"items": [item]})
                assert bulk.status_code == 422, (item, bulk.text)
        assert [c["key"] for c in ok(owner.get(url(f"/products/{p}/cases")))["items"]] == ["PAY-1"]
        assert ok(owner.get(url("/cases/PAY-1")))["title"] == "Pay by card"

    @test()
    def test_spaces_around_a_title_are_stripped(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, f = s["product"]["id"], s["child"]["id"]
        assert make_case(owner, p, f, "  Pay by card \t")["title"] == "Pay by card"
        assert ok(patch(owner, "PAY-1", 1, {"title": " Pay by saved card  "}))["title"] == "Pay by saved card"
        same = patch(owner, "PAY-1", 2, {"title": "  Pay by saved card"})
        assert ok(same)["current_version"] == 2  # the same title once stripped adds no version
        body = {"items": [{"feature_id": f, "title": " Refund "}]}
        assert ok(owner.post(url(f"/products/{p}/cases/bulk"), json=body))["items"][0]["key"] == "PAY-2"
        assert ok(owner.get(url("/cases/PAY-2")))["title"] == "Refund"
        long = " " + "x" * 500 + " "
        assert make_case(owner, p, f, long)["title"] == "x" * 500  # the limit counts after stripping

    @test()
    def test_case_writes_need_write_cases_and_stay_in_the_org(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        make_case(owner, s["product"]["id"], s["child"]["id"])
        add_member(owner, "viewer@example.com", "viewer")
        token = ok(
            owner.post(url("/tokens"), json={"name": "ro", "scopes": ["read"]}),
            201,
        )["token"]
        reader = self.env.bearer(token)
        assert reader.get(url("/cases/PAY-1")).status_code == 200
        assert patch(reader, "PAY-1", 1, {"title": "x"}).status_code == 403
        p = s["product"]["id"]
        assert (
            reader.post(
                url(f"/products/{p}/cases"), json={"feature_id": s["child"]["id"], "title": "x"}
            ).status_code
            == 403
        )
        assert owner.get(url("/cases/PAY-1", "globex")).status_code in (403, 404)

    @test()
    def test_case_versions_refuse_orm_and_core_writes(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        app = self.env.app
        make_case(owner, s["product"]["id"], s["child"]["id"], tags=["smoke"])
        with app.state.sessionmaker() as db:
            v = db.scalar(select(CaseVersion))
            v.title = "rewritten"
            with support.raises(CaseVersionImmutableError):
                db.flush()
            db.rollback()
            db.delete(db.scalar(select(CaseVersion)))
            with support.raises(CaseVersionImmutableError):
                db.flush()
            db.rollback()
            for statement in (
                update(CaseVersion).values(title="x"),
                delete(CaseVersion),
                update(CaseVersionTag).values(tag_id="x"),
                delete(CaseVersionTag),
            ):
                with support.raises(CaseVersionImmutableError):
                    db.execute(statement)
                db.rollback()
        assert ok(owner.get(url("/cases/PAY-1")))["title"] == "Pay by card"

    # Description

    @test()
    def test_description_is_versioned_and_restored_like_the_other_fields(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        make_case(owner, s["product"]["id"], s["child"]["id"], description={"markdown": "Card payments"})
        assert ok(owner.get(url("/cases/PAY-1")))["description"].strip() == "Card payments"
        assert (
            ok(patch(owner, "PAY-1", 1, {"preconditions": {"markdown": "Logged in"}}))["description"].strip()
            == "Card payments"
        )  # a field left out keeps its value
        edited = ok(patch(owner, "PAY-1", 2, {"description": {"markdown": "Card and wallet payments"}}))
        assert (edited["current_version"], edited["description"].strip()) == (3, "Card and wallet payments")
        assert ok(owner.get(url("/cases/PAY-1/versions/1")))["description"].strip() == "Card payments"
        restored = ok(owner.post(url("/cases/PAY-1/restore"), json={"version": 1}, headers={"If-Match": "3"}))
        assert (restored["current_version"], restored["description"].strip()) == (4, "Card payments")
        assert (
            make_case(owner, s["product"]["id"], s["child"]["id"], title="Plain")["description"].strip() == ""
        )

    # One case as Markdown

    @test()
    def test_markdown_get_and_put_edit_the_case_through_the_bundle_parser(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        case = make_case(
            owner,
            s["product"]["id"],
            s["child"]["id"],
            description={"markdown": "Card payments"},
            steps=STEPS,
        )
        r = owner.get(url("/cases/PAY-1/markdown"))
        got = ok(r)
        assert r.headers["ETag"] == '"1"'
        assert (got["case_id"], got["key"], got["version"]) == (case["id"], "PAY-1", 1)
        text = got["markdown"]
        assert " description -->\nCard payments" in text and "\n# Pay by card\n" in text
        edited = text.replace("# Pay by card", "# Pay by debit card").replace("Card payments", "Debit only")
        r = put_markdown(owner, "PAY-1", 1, edited, change_note="from the editor")
        saved = ok(r)
        assert r.headers["ETag"] == '"2"'
        assert (saved["current_version"], saved["title"], saved["description"].strip()) == (
            2,
            "Pay by debit card",
            "Debit only",
        )
        assert [st["id"] for st in saved["steps"]] == [st["id"] for st in case["steps"]]
        assert ok(owner.get(url("/cases/PAY-1/versions/2")))["change_note"] == "from the editor"
        assert [e["action"] for e in events(owner, "test_case")][-1] == "case.update"
        same = ok(owner.get(url("/cases/PAY-1/markdown")))["markdown"]
        assert ok(put_markdown(owner, "PAY-1", 2, same))["current_version"] == 2  # unchanged: no version

    @test()
    def test_markdown_put_without_a_description_section_keeps_the_description(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        make_case(owner, s["product"]["id"], s["child"]["id"], description={"markdown": "Card payments"})
        text = ok(owner.get(url("/cases/PAY-1/markdown")))["markdown"]
        old = drop_section(text, "description").replace("# Pay by card", "# Renamed")
        saved = ok(put_markdown(owner, "PAY-1", 1, old))
        assert (saved["current_version"], saved["title"], saved["description"].strip()) == (
            2,
            "Renamed",
            "Card payments",
        )

    @test()
    def test_markdown_put_refuses_stale_wrong_case_moved_archived_and_read_only(self, suite_parameter):
        owner = self.env.owner
        s = self.s()
        p, f = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, f)
        make_case(owner, p, f, title="Second")
        text = ok(owner.get(url("/cases/PAY-1/markdown")))["markdown"]
        ok(patch(owner, "PAY-1", 1, {"title": "Moved on"}))
        assert put_markdown(owner, "PAY-1", 1, text).status_code == 409  # If-Match is stale
        stale = put_markdown(owner, "PAY-1", 2, text)  # the file is still at version 1
        assert stale.status_code == 422 and stale.json()["errors"][0]["column"] == "version"
        text = ok(owner.get(url("/cases/PAY-1/markdown")))["markdown"]
        other = ok(owner.get(url("/cases/PAY-2/markdown")))["markdown"]
        wrong = put_markdown(owner, "PAY-1", 2, other)
        assert wrong.status_code == 422 and wrong.json()["errors"][0]["column"] == "key"
        moved = text.replace('feature: "Checkout > Card"', 'feature: "Checkout"')
        assert moved != text
        bad = put_markdown(owner, "PAY-1", 2, moved)
        assert bad.status_code == 422 and bad.json()["errors"][0]["column"] == "feature"
        broken = put_markdown(owner, "PAY-1", 2, "no front matter")
        assert broken.status_code == 422
        token = ok(owner.post(url("/tokens"), json={"name": "ro", "scopes": ["read"]}), 201)["token"]
        reader = self.env.bearer(token)
        assert reader.get(url("/cases/PAY-1/markdown")).status_code == 200
        assert put_markdown(reader, "PAY-1", 2, text).status_code == 403
        ok(owner.post(url("/cases/PAY-1/archive")))
        assert put_markdown(owner, "PAY-1", 2, text).status_code == 409
        assert ok(owner.get(url("/cases/PAY-1")))["current_version"] == 2


def put_markdown(client, case: str, version: int, markdown: str, org: str = "acme", **body):
    return client.put(
        url(f"/cases/{case}/markdown", org),
        json={"markdown": markdown, **body},
        headers={"If-Match": f'"{version}"'},
    )


def drop_section(text: str, name: str) -> str:
    """The bundle file without one section: its marker line and the lines up to the next marker."""
    out, dropping = [], False
    for line in text.split("\n"):
        if line.startswith("<!-- tcms-"):
            dropping = line.endswith(f" {name} -->")
        if not dropping:
            out.append(line)
    return "\n".join(out)


def walk(client, product: str, **params) -> tuple[list[str], set[int]]:
    """Every case key of the list, read two to a page so the cursor is crossed, and each page's total."""
    keys, totals, cursor = [], set(), None
    while True:
        page = ok(
            client.get(url(f"/products/{product}/cases"), params={**params, "limit": 2, "cursor": cursor})
        )
        keys += [c["key"] for c in page["items"]]
        totals.add(page["total"])
        cursor = page["next_cursor"]
        if cursor is None:
            return keys, totals


def set_updated_at(app, number: int, when: datetime) -> None:
    with app.state.sessionmaker() as db:
        db.execute(update(TestCase).where(TestCase.number == number).values(updated_at=when))
        db.commit()


def positions(client, *keys: str) -> list[int]:
    return [ok(client.get(url(f"/cases/{k}")))["position"] for k in keys]


@Suite(parameters=support.DATABASES)
class CaseLists:
    """F1: totals, filters, sorts, key search and manual position on the cases list."""

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
    def test_total_counts_the_filtered_list_across_pages(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, f = s["product"]["id"], s["child"]["id"]
        for i in range(5):
            make_case(owner, p, f, f"Case {i}", priority="high" if i < 3 else "low")
        keys, totals = walk(owner, p)
        assert (keys, totals) == (["PAY-1", "PAY-2", "PAY-3", "PAY-4", "PAY-5"], {5})
        keys, totals = walk(owner, p, priority="high")
        assert (keys, totals) == (["PAY-1", "PAY-2", "PAY-3"], {3})
        assert ok(owner.get(url("/products")))["total"] == 1
        assert ok(owner.get(url("/cases/PAY-1/versions")))["total"] == 1

    @test()
    def test_result_filter_reads_the_last_result_in_any_cycle(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, f = s["product"]["id"], s["child"]["id"]
        cases = [make_case(owner, p, f, t)["id"] for t in ("Failed", "Passed", "Never run")]
        cycle = make_cycle(owner, p, case_ids=cases[:2])
        by_case = {cc["case_id"]: cc["id"] for cc in cycle_cases(owner, cycle["id"])}
        ok(record(owner, by_case[cases[0]], status="success"), 201)
        ok(record(owner, by_case[cases[0]], status="fail"), 201)  # the newest result wins
        ok(record(owner, by_case[cases[1]], status="success"), 201)
        assert walk(owner, p, result="fail") == (["PAY-1"], {1})
        assert walk(owner, p, result=["success", "untested"]) == (["PAY-2", "PAY-3"], {2})
        listed = ok(owner.get(url(f"/products/{p}/cases")))["items"]
        assert [c["last_result"] for c in listed] == ["fail", "success", None]
        assert owner.get(url(f"/products/{p}/cases"), params={"result": "nope"}).status_code == 422

    @test()
    def test_priority_updated_since_and_has_ref_filters(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, f = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, f, "A", priority="critical", automation_ref="tests/a.py::A")
        make_case(owner, p, f, "B", priority="low")
        make_case(owner, p, f, "C", priority="low", automation_ref="")
        set_updated_at(self.env.app, 1, datetime(2026, 1, 1, tzinfo=UTC))
        set_updated_at(self.env.app, 2, datetime(2026, 3, 1, tzinfo=UTC))
        set_updated_at(self.env.app, 3, datetime(2026, 5, 1, tzinfo=UTC))
        assert walk(owner, p, priority=["critical", "high"]) == (["PAY-1"], {1})
        assert owner.get(url(f"/products/{p}/cases"), params={"priority": "urgent"}).status_code == 422
        assert walk(owner, p, updated_since="2026-03-01T00:00:00Z") == (["PAY-2", "PAY-3"], {2})
        assert walk(owner, p, updated_since="2026-02-28T16:00:00-08:00") == (["PAY-2", "PAY-3"], {2})
        assert walk(owner, p, has_ref=True) == (["PAY-1"], {1})
        assert walk(owner, p, has_ref=False) == (["PAY-2", "PAY-3"], {2})

    @test()
    def test_edited_by_reads_who_made_the_current_version(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, f = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, f, "Mine")
        make_case(owner, p, f, "Agent's")
        agent = ok(owner.post(url("/agents"), json={"name": "bot", "role": "editor"}), 201)
        scopes = ["read", "write:cases"]
        body = {"name": "bot", "scopes": scopes, "actor_id": agent["id"]}
        token = ok(owner.post(url("/tokens"), json=body), 201)["token"]
        ok(patch(self.env.bearer(token), "PAY-2", 1, {"title": "Agent's v2"}))
        me = ok(owner.get(url("/cases/PAY-1/versions/1")))["created_by_actor_id"]
        assert ok(owner.get(url("/cases/PAY-2/versions/2")))["created_by_actor_id"] == agent["id"]
        assert walk(owner, p, edited_by=agent["id"]) == (["PAY-2"], {1})
        assert walk(owner, p, edited_by=[agent["id"], me]) == (["PAY-1", "PAY-2"], {2})
        assert walk(owner, p, edited_by_kind="agent") == (["PAY-2"], {1})
        assert walk(owner, p, edited_by_kind="user") == (["PAY-1"], {1})

    @test()
    def test_each_sort_pages_in_order(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, f = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, f, "banana", priority="low")
        make_case(owner, p, f, "Apple", priority="critical")
        make_case(owner, p, f, "cherry", priority="high")
        make_case(owner, p, f, "date", priority="low")
        cycle = make_cycle(owner, p, case_ids=[ok(owner.get(url(f"/cases/PAY-{n}")))["id"] for n in (3, 4)])
        by_key = {cc["key"]: cc["id"] for cc in cycle_cases(owner, cycle["id"])}
        ok(record(owner, by_key["PAY-3"], status="success"), 201)
        ok(record(owner, by_key["PAY-4"], status="fail"), 201)
        for n, month in ((1, 4), (2, 2), (3, 3), (4, 1)):
            set_updated_at(self.env.app, n, datetime(2026, month, 1, tzinfo=UTC))
        total = {4}
        assert walk(owner, p, sort="key") == (["PAY-1", "PAY-2", "PAY-3", "PAY-4"], total)
        assert walk(owner, p, sort="title") == (["PAY-2", "PAY-1", "PAY-3", "PAY-4"], total)
        assert walk(owner, p, sort="updated") == (["PAY-1", "PAY-3", "PAY-2", "PAY-4"], total)
        assert walk(owner, p, sort="result") == (["PAY-4", "PAY-1", "PAY-2", "PAY-3"], total)
        assert walk(owner, p, sort="priority") == (["PAY-2", "PAY-3", "PAY-1", "PAY-4"], total)
        ok(owner.post(url("/cases/PAY-4/move"), json={"feature_id": f, "position": 0}))
        assert walk(owner, p, sort="manual") == (["PAY-4", "PAY-1", "PAY-2", "PAY-3"], total)

    @test()
    def test_manual_sort_follows_the_tree_over_a_subtree(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)  # Checkout > Card
        p, parent, card = s["product"]["id"], s["parent"]["id"], s["child"]["id"]
        wallet = make_feature(owner, p, "Wallet", parent_id=parent)["id"]
        other = make_feature(owner, p, "Other")["id"]
        make_case(owner, p, other, "o1")  # PAY-1: in a later top-level feature
        make_case(owner, p, wallet, "w1")  # PAY-2
        make_case(owner, p, card, "c1")  # PAY-3
        make_case(owner, p, parent, "p1")  # PAY-4
        make_case(owner, p, card, "c2")  # PAY-5
        # Pre-order: Checkout (p1), Card (c1, c2), Wallet (w1), Other (o1).
        assert walk(owner, p, sort="manual") == (["PAY-4", "PAY-3", "PAY-5", "PAY-2", "PAY-1"], {5})
        assert walk(owner, p, sort="manual", feature=parent) == (["PAY-4", "PAY-3", "PAY-5", "PAY-2"], {4})
        ok(owner.post(url(f"/features/{wallet}/move"), json={"parent_id": parent, "position": 0}))
        assert walk(owner, p, sort="manual", feature=parent) == (["PAY-4", "PAY-2", "PAY-3", "PAY-5"], {4})

    @test()
    def test_key_search_matches_key_number_steps_and_tags(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, f = s["product"]["id"], s["child"]["id"]
        make_case(owner, p, f, "Pay by card", steps=STEPS)
        make_case(owner, p, f, "Refund", tags=["smoke", "smoke-eu"])
        for n in range(10):
            make_case(owner, p, f, f"Filler {'abcdefghij'[n]}")  # PAY-3 to PAY-12, no digit in the title
        assert walk(owner, p, q="PAY-12") == (["PAY-12"], {1})
        assert walk(owner, p, q="pay-2") == (["PAY-2"], {1})
        assert walk(owner, p, q="2") == (["PAY-2"], {1})  # a number is a key, not a part of one
        assert walk(owner, p, q="open checkout") == (["PAY-1"], {1})
        assert walk(owner, p, q="SMOKE") == (["PAY-2"], {1})  # two matching tags still count once
        assert walk(owner, p, q="refund") == (["PAY-2"], {1})
        assert walk(owner, p, q="9999999999") == ([], {0})
        assert walk(owner, p, q="OTHER-1") == ([], {0})

    @test()
    def test_position_is_read_appended_and_reordered(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, card, parent = s["product"]["id"], s["child"]["id"], s["parent"]["id"]
        for t in ("a", "b", "c"):
            make_case(owner, p, card, t)
        make_case(owner, p, parent, "d")
        assert positions(owner, "PAY-1", "PAY-2", "PAY-3", "PAY-4") == [0, 1, 2, 0]
        ok(owner.post(url("/cases/PAY-3/move"), json={"feature_id": card, "position": 0}))
        assert positions(owner, "PAY-3", "PAY-1", "PAY-2") == [0, 1, 2]
        moved = ok(owner.post(url("/cases/PAY-1/move"), json={"feature_id": parent, "position": 0}))
        assert (moved["feature_id"], moved["position"]) == (parent, 0)
        assert positions(owner, "PAY-1", "PAY-4", "PAY-3", "PAY-2") == [0, 1, 0, 1]
        ok(owner.post(url("/cases/PAY-2/move"), json={"feature_id": parent}))  # no position: to the end
        assert positions(owner, "PAY-1", "PAY-4", "PAY-2", "PAY-3") == [0, 1, 2, 0]
        ok(owner.post(url("/cases/PAY-3/move"), json={"feature_id": card, "position": 99}))
        assert positions(owner, "PAY-3") == [0]
        assert make_case(owner, p, parent, "e")["position"] == 3
        moves = [e["changes"] for e in events(owner, "test_case") if e["action"] == "case.move"]
        assert sorted(m["position"] for m in moves) == [
            [1, 0],
            [1, 2],
            [2, 0],
        ]  # the no-op move to 99 records nothing

    @test()
    def test_reorder_keeps_the_other_cases_updated_at(self, suite_parameter):
        owner = self.env.owner
        s = seed(owner)
        p, card, parent = s["product"]["id"], s["child"]["id"], s["parent"]["id"]
        for t in ("a", "b", "c"):
            make_case(owner, p, card, t)
        old = datetime(2026, 1, 1, tzinfo=UTC)
        for n in (1, 2, 3):
            set_updated_at(self.env.app, n, old)
        ok(owner.post(url("/cases/PAY-3/move"), json={"feature_id": card, "position": 0}))
        assert positions(owner, "PAY-3", "PAY-1", "PAY-2") == [0, 1, 2]
        assert walk(owner, p, updated_since="2026-02-01T00:00:00Z") == ([], {0})
        ok(owner.post(url("/cases/PAY-3/move"), json={"feature_id": parent}))
        assert positions(owner, "PAY-1", "PAY-2") == [0, 1]
        assert walk(owner, p, updated_since="2026-02-01T00:00:00Z") == (["PAY-3"], {1})  # only the moved one
