"""Web adapter for the Cases list, run in node against a live server: the state each URL gives, the
mapped rows, and that the search, filters, sort and paging are the server's (the adapter passes them
on), plus a raw error."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.web.live import LiveServer, as_sent, run_js

ORG = "/api/v1/orgs/acme"


@Suite(parameters=support.DATABASES)
class WebCasesAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def post(self, path, body):
        response = self.live.owner.post(f"{ORG}{path}", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def seed(self):
        """PAY with Checkout › Card payments and Refunds, and three cases; returns (features, cases)
        by name/key."""
        self.post("/products", {"key": "PAY", "name": "Payments"})
        checkout = self.post("/products/PAY/features", {"name": "Checkout"})
        card = self.post("/products/PAY/features", {"name": "Card payments", "parent_id": checkout["id"]})
        refunds = self.post("/products/PAY/features", {"name": "Refunds"})
        cases = [
            self.post(
                "/products/PAY/cases",
                {
                    "feature_id": card["id"],
                    "title": "Pay with a saved Visa card",
                    "status": "ready",
                    "priority": "high",
                    "tags": ["smoke"],
                },
            ),
            self.post(
                "/products/PAY/cases",
                {"feature_id": card["id"], "title": "Card is declined", "status": "draft", "priority": "low"},
            ),
            self.post(
                "/products/PAY/cases",
                {
                    "feature_id": refunds["id"],
                    "title": "Partial refund of one line item",
                    "status": "ready",
                    "automation": "automated",
                    "priority": "medium",
                },
            ),
        ]
        features = {"checkout": checkout, "card": card, "refunds": refunds}
        return features, {c["title"]: c for c in cases}

    def load(self, params):
        """{ out: the adapter's { state, data }, asked: the cases_list URLs it called }, as the acme owner."""
        return run_js(
            self.live,
            f"""await h.signIn();
            const params = {json.dumps({"product": "PAY", **params})};
            const ctx = await h.ctx(params);
            const out = await (await h.adapter("cases")).load(params, ctx);
            const asked = h.calls.map((c) => c.path).filter((p) => p.includes("/products/PAY/cases"));
            return {{ out, asked }};""",
            "/app?view=cases&product=PAY",
        )

    @test()
    def test_no_cases_is_the_empty_state(self, suite_parameter):
        self.post("/products", {"key": "PAY", "name": "Payments"})
        out = self.load({})["out"]
        assert out["state"] == "empty"
        assert (out["data"]["total"], out["data"]["matched"], out["data"]["cases"]) == (0, 0, [])
        assert out["data"]["product"] == {"key": "PAY", "name": "Payments"}

    @test()
    def test_list_maps_each_case_to_its_row(self, suite_parameter):
        features, cases = self.seed()
        got = self.load({})
        out = got["out"]
        assert out["state"] == "list"
        d = out["data"]
        assert (d["total"], d["matched"], d["shown"], d["sort"], d["q"]) == (3, 3, 50, "updated", "")
        assert d["filter"] == {"feature": [], "status": [], "result": [], "automation": [], "priority": []}
        rows = {r["key"]: r for r in d["cases"]}
        visa = cases["Pay with a saved Visa card"]
        row = rows[visa["key"]]
        assert row["id"] == visa["id"]
        assert (row["title"], row["feature"], row["version"]) == (
            "Pay with a saved Visa card",
            "Checkout › Card payments",
            1,
        )
        assert (row["status"], row["priority"], row["automation"], row["tags"]) == (
            "ready",
            "high",
            "manual",
            ["smoke"],
        )
        assert row["result"] == "untested" and row["updated"]
        assert d["features"] == [
            {"id": features["checkout"]["id"], "path": "Checkout", "cases": 2},
            {
                "id": features["card"]["id"],
                "path": "Checkout › Card payments",
                "short": "Card payments",
                "cases": 2,
            },
            {"id": features["refunds"]["id"], "path": "Refunds", "cases": 1},
        ]
        assert any("sort=updated" in p and "limit=50" in p for p in got["asked"]), got["asked"]
        assert self.load({"ui": "search-cleared"})["out"]["state"] == "search-cleared"
        assert self.load({"ui": "filter-open"})["out"]["state"] == "filter-open"

    @test()
    def test_search_is_the_servers_q_on_key_and_title(self, suite_parameter):
        _, cases = self.seed()
        got = self.load({"q": "refund"})
        out = got["out"]
        assert out["state"] == "search"
        assert [r["title"] for r in out["data"]["cases"]] == ["Partial refund of one line item"]
        assert (out["data"]["matched"], out["data"]["total"]) == (1, 3)
        assert any("q=refund" in p for p in got["asked"]), got["asked"]
        key = cases["Card is declined"]["key"]
        by_key = self.load({"q": key})["out"]
        assert [r["key"] for r in by_key["data"]["cases"]] == [key]
        none = self.load({"q": "invoice"})["out"]
        assert none["state"] == "search-empty"
        assert (none["data"]["cases"], none["data"]["matched"], none["data"]["total"]) == ([], 0, 3)

    @test()
    def test_filters_and_sort_are_the_servers(self, suite_parameter):
        features, _ = self.seed()
        got = self.load(
            {
                "feature": features["checkout"]["id"],
                "status": "ready,draft",
                "priority": "high",
                "sort": "title",
            }
        )
        out = got["out"]
        assert out["state"] == "filtered"
        d = out["data"]
        assert d["filter"]["feature"] == [features["checkout"]["id"]]
        assert d["filter"]["status"] == ["ready", "draft"] and d["filter"]["priority"] == ["high"]
        assert [r["title"] for r in d["cases"]] == ["Pay with a saved Visa card"]
        assert (d["matched"], d["total"]) == (1, 3)
        asked = [p for p in got["asked"] if "limit=50" in p]
        assert len(asked) == 1, got["asked"]
        parts = (f"feature={features['checkout']['id']}", "status=ready", "status=draft", "priority=high")
        for part in (*parts, "sort=title"):
            assert part in asked[0], asked[0]
        auto = self.load({"automation": "automated", "result": "untested", "sort": "key"})["out"]
        assert [r["title"] for r in auto["data"]["cases"]] == ["Partial refund of one line item"]
        titles = [r["title"] for r in self.load({"sort": "title"})["out"]["data"]["cases"]]
        assert titles == ["Card is declined", "Partial refund of one line item", "Pay with a saved Visa card"]
        none = self.load({"status": "deprecated"})["out"]
        assert none["state"] == "filtered" and none["data"]["cases"] == []

    @test()
    def test_shown_pages_through_the_server(self, suite_parameter):
        self.seed()
        got = self.load({"shown": "120"})
        assert got["out"]["data"]["shown"] == 120 and len(got["out"]["data"]["cases"]) == 3
        assert any("limit=120" in p for p in got["asked"]), got["asked"]

    @test()
    def test_unknown_filter_value_is_the_raw_error(self, suite_parameter):
        self.seed()
        out = run_js(
            self.live,
            """await h.signIn();
            const params = { product: "PAY", priority: "urgent" };
            const ctx = await h.ctx(params);
            return h.fail((await h.adapter("cases")).load(params, ctx));""",
            "/app?view=cases&product=PAY",
        )
        raw = self.live.owner.get(f"{ORG}/products/PAY/cases", params={"priority": "urgent"})
        assert raw.status_code >= 400, raw.text
        assert out == {"name": "ApiError", "status": raw.status_code, "raw": as_sent(raw)}
