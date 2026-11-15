"""Test cases: every content edit adds an immutable version, read back as history or one version (T3)."""

from sqlalchemy import delete, select, update
from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from test_junkie_tcms.db.models import CaseVersion, CaseVersionTag, Tag, TestCase
from test_junkie_tcms.db.session import CaseVersionImmutableError
from tests import support
from tests.catalog_seed import events, make_feature, make_product, ok, seed, url
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
