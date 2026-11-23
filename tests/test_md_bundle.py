"""T6b md-bundle: a zip of one Markdown file per case, that imports back with the same content."""

import base64
import io
import json
import re
import zipfile

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.catalog_seed import make_product, ok, url
from tests.execution_seed import make_case
from tests.test_csv_io import cases_count, comparable, export, rows, source


def bundle(client, product: str, **body) -> dict[str, str]:
    r = client.post(url(f"/products/{product}/exports"), json={"format": "md-bundle", **body})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        return {name: zf.read(name).decode() for name in zf.namelist()}


def to_zip(files: dict[str, str]) -> str:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return base64.b64encode(out.getvalue()).decode()


def do_import(client, product: str, encoded: str, **body):
    return client.post(
        url(f"/products/{product}/imports"), json={"format": "md-bundle", "bundle": encoded, **body}
    )


def keyless(text: str) -> str:
    """A bundle file as a new case: no key, no version and no step ids."""
    text = re.sub(r"^key: .*$", "key: null", text, count=1, flags=re.M)
    text = re.sub(r"^version: .*$", "version: null", text, count=1, flags=re.M)
    return re.sub(r"^(<!-- tcms-[0-9a-f]+ step) \S+ (action|expected) -->$", r"\1 \2 -->", text, flags=re.M)


@Suite(parameters=support.DATABASES)
class MdBundle:
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
    def test_bundle_has_a_file_per_case(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        files = bundle(owner, s["product"]["id"])
        assert sorted(files) == ["PAY-1.md", "PAY-2.md"]
        first = files["PAY-1.md"]
        assert first.startswith('---\nkey: "PAY-1"\nversion: 1\nfeature: "Checkout > Card"\n')
        assert "\n# Pay by card\n" in first
        assert "- a coupon" in first

    @test()
    def test_round_trip_into_another_product(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        files = bundle(owner, p)
        target = make_product(owner, "NEW")
        fresh = {name: keyless(text) for name, text in files.items()}
        out = ok(do_import(owner, target["id"], to_zip(fresh), create_features=True))
        assert (out["created"], out["keys"]) == (2, ["NEW-1", "NEW-2"])
        assert [comparable(r) for r in rows(export(owner, target["id"]))] == [
            comparable(r) for r in rows(export(owner, p))
        ]

    @test()
    def test_reimport_into_the_same_product_is_unchanged(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        before = export(owner, p)
        out = ok(do_import(owner, p, to_zip(bundle(owner, p))))
        assert (out["created"], out["updated"], out["unchanged"]) == (0, 0, 2)
        assert export(owner, p) == before  # no new versions, steps keep their ids

    @test()
    def test_edited_file_updates_the_case(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        files = bundle(owner, p)
        files["PAY-1.md"] = files["PAY-1.md"].replace("# Pay by card", "# Pay by saved card")
        files["PAY-2.md"] += (
            "<!-- "
            + re.search(r'boundary: "(.+)"', files["PAY-2.md"]).group(1)
            + " step action -->\nTap pay\n"
        )
        out = ok(do_import(owner, p, to_zip(files)))
        assert (out["created"], out["updated"], out["unchanged"]) == (0, 2, 0)
        got = rows(export(owner, p))
        assert (got[0]["title"], got[0]["version"]) == ("Pay by saved card", "2")
        assert [s["action"] for s in json.loads(got[1]["steps"])] == ["Tap pay"]

    @test()
    def test_stale_version_writes_nothing(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        files = bundle(owner, p)
        ok(owner.patch(url("/cases/PAY-1"), json={"title": "Edited since"}, headers={"If-Match": '"1"'}))
        files["PAY-2.md"] = files["PAY-2.md"].replace("# Checkout", "# Fine edit")
        r = do_import(owner, p, to_zip(files))
        assert r.status_code == 422, r.text
        errors = r.json()["errors"]
        assert [(e["row"], e["column"]) for e in errors] == [(1, "version")]
        assert errors[0]["detail"].startswith("PAY-1.md: ")
        assert ok(owner.get(url("/cases/PAY-2")))["current_version"] == 1

    @test()
    def test_a_title_line_of_only_spaces_writes_nothing(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        files = bundle(owner, p)
        files["PAY-1.md"] = re.sub(r"^# .*$", "#    ", files["PAY-1.md"], count=1, flags=re.M)
        files["NEW.md"] = re.sub(r"^# .*$", "#  \t", keyless(files["PAY-2.md"]), count=1, flags=re.M)
        r = do_import(owner, p, to_zip(files))
        assert r.status_code == 422, r.text
        errors = r.json()["errors"]
        assert sorted((e["detail"].split(":")[0], e["column"]) for e in errors) == [
            ("NEW.md", "title"),
            ("PAY-1.md", "title"),
        ]
        assert ok(owner.get(url("/cases/PAY-1")))["title"] == "Pay by card"
        assert cases_count(owner, p) == 2

    @test()
    def test_boundary_collision_still_round_trips(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        first = bundle(owner, p)["PAY-2.md"]
        taken = re.search(r'boundary: "(.+)"', first).group(1)
        tricky = f"```\n<!-- {taken} preconditions -->\n<!-- {taken} step x action -->\n```"
        make_case(owner, p, s["parent"]["id"], "Tricky", preconditions={"markdown": tricky})
        files = bundle(owner, p)
        third = files["PAY-3.md"]
        boundary = re.search(r'boundary: "(.+)"', third).group(1)
        assert boundary != taken and taken in third
        before = export(owner, p)
        out = ok(do_import(owner, p, to_zip(files)))
        assert out["unchanged"] == 3
        assert export(owner, p) == before
        assert rows(before)[2]["preconditions"] == tricky

    @test()
    def test_zip_limits_write_nothing(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        files = {name: keyless(text) for name, text in bundle(owner, p).items()}
        big = io.BytesIO()
        with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("big.md", "x" * (21 * 1024 * 1024))
        cases = [
            (base64.b64encode(b"\0" * (5 * 1024 * 1024 + 1)).decode(), 413),
            (base64.b64encode(big.getvalue()).decode(), 413),
            (to_zip({**files, "../x.md": files["PAY-1.md"]}), 422),
            (to_zip({**files, "/x.md": files["PAY-1.md"]}), 422),
            ("not base64!", 422),
            (base64.b64encode(b"not a zip").decode(), 422),
            (to_zip({"notes.txt": "hi"}), 422),
            (to_zip({**files, "bad.md": "no front matter"}), 422),
        ]
        for encoded, status in cases:
            r = do_import(owner, p, encoded, create_features=True)
            assert r.status_code == status, (status, r.text[:300])
        assert cases_count(owner, p) == 2

    @test()
    def test_refused_requests(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        encoded = to_zip(bundle(owner, p))
        assert do_import(owner, p, encoded, mapping={"Title": "title"}).status_code == 422
        assert do_import(owner, p, encoded, csv="key\n").status_code == 422
        bad = {"PAY-1.md": "---\nkey: 1\n---\n# x\n"}
        r = do_import(owner, p, to_zip(bad))
        assert r.status_code == 422, r.text
        assert [(e["row"], e["column"]) for e in r.json()["errors"]] == [(1, "key")]

    @test()
    def test_subtree_and_archived(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        assert sorted(bundle(owner, p, feature=s["child"]["id"])) == ["PAY-1.md"]
        ok(owner.post(url("/cases/PAY-1/archive")))
        assert sorted(bundle(owner, p)) == ["PAY-2.md"]
        assert sorted(bundle(owner, p, include_archived=True)) == ["PAY-1.md", "PAY-2.md"]

    @test()
    def test_title_with_a_line_break_is_refused(self, suite_parameter):
        owner = self.env.owner
        s = source(owner)
        p = s["product"]["id"]
        make_case(owner, p, s["parent"]["id"], "Two\nlines")
        r = owner.post(url(f"/products/{p}/exports"), json={"format": "md-bundle"})
        assert r.status_code == 422, r.text
        assert "PAY-3" in r.text
