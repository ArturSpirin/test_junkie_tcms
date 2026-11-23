"""Web adapter for the Case editor, run in node against a live server: the state each URL gives, the case
mapped onto the editor's shape (rich text, provenance, where it sits), the writes (save, Markdown save,
create) read back from the server, and refused saves shown raw."""

import json

from test_junkie.decorators import Suite, afterClass, afterTest, beforeTest, test

from tests import support
from tests.web.live import LiveServer, as_sent, run_js

ORG = "/api/v1/orgs/acme"


@Suite(parameters=support.DATABASES)
class WebCaseAdapter:
    @beforeTest()
    def start(self, suite_parameter):
        self.live = LiveServer(suite_parameter)

    @afterTest()
    def stop(self):
        self.live.close()

    @afterClass()
    def sweep(self):
        support.close_all()

    def call(self, method, path, body=None, status=(200, 201), **kw):
        response = self.live.owner.request(method, f"{ORG}{path}", json=body, **kw)
        assert response.status_code in status, response.text
        return response.json()

    def seed(self):
        """PAY with Checkout › Card payments and Refunds, PAY-1 in Card payments (rich text, two steps, a tag
        and a link), 2.14.0 covering Checkout, a plan by feature, a plan by case and an open cycle."""
        self.call("POST", "/products", {"key": "PAY", "name": "Payments"})
        checkout = self.call("POST", "/products/PAY/features", {"name": "Checkout"})
        card = self.call(
            "POST", "/products/PAY/features", {"name": "Card payments", "parent_id": checkout["id"]}
        )
        refunds = self.call("POST", "/products/PAY/features", {"name": "Refunds"})
        case = self.call(
            "POST",
            "/products/PAY/cases",
            {
                "feature_id": card["id"],
                "title": "Pay with a saved Visa card",
                "status": "ready",
                "priority": "high",
                "tags": ["smoke"],
                "links": [{"url": "https://tracker.example.com/PAY-2210", "key": "PAY-2210"}],
                "description": {"markdown": "A returning customer pays with a **saved** card."},
                "preconditions": {"markdown": "- Stripe test mode\n- Visa ending 4242"},
                "steps": [
                    {
                        "action": {"markdown": "Open **Checkout**"},
                        "expected": {"markdown": "The summary shows `$42.00`"},
                    },
                    {"action": {"markdown": "Press *Pay now*"}, "expected": {"markdown": "Payment succeeds"}},
                ],
            },
        )
        rel = self.call(
            "POST", "/products/PAY/releases", {"version": "2.14.0", "name": "Winter", "status": "in_progress"}
        )
        self.call("PUT", f"/releases/{rel['id']}/features", {"feature_ids": [checkout["id"]]})
        self.call("POST", "/products/PAY/releases", {"version": "2.15.0", "name": "Spring"})
        by_feature = self.call(
            "POST", "/products/PAY/plans", {"name": "Checkout regression", "release_id": rel["id"]}
        )
        self.call("POST", f"/plans/{by_feature['id']}/entries", {"entries": [{"feature_id": checkout["id"]}]})
        by_case = self.call("POST", "/products/PAY/plans", {"name": "Release smoke"})
        self.call("POST", f"/plans/{by_case['id']}/entries", {"entries": [{"case_id": case["id"]}]})
        other = self.call("POST", "/products/PAY/plans", {"name": "Refunds only"})
        self.call("POST", f"/plans/{other['id']}/entries", {"entries": [{"feature_id": refunds["id"]}]})
        cycle = self.call(
            "POST", "/products/PAY/cycles", {"name": "Checkout · staging", "case_ids": [case["id"]]}
        )
        return {
            "checkout": checkout,
            "card": card,
            "refunds": refunds,
            "case": case,
            "release": rel,
            "by_feature": by_feature,
            "by_case": by_case,
            "cycle": cycle,
        }

    def js(self, body, params, who=""):
        """Run body signed in (the owner, or who) with params, ctx and A (the case adapter) in scope."""
        sign_in = f'await h.signIn("{who}");' if who else "await h.signIn();"
        return run_js(
            self.live,
            f"""{sign_in}
            const params = {json.dumps({"product": "PAY", **params})};
            const ctx = await h.ctx(params);
            const A = await h.adapter("case");
            {body}""",
            "/app?view=case&product=PAY",
        )

    def load(self, params, who=""):
        return self.js("return A.load(params, ctx);", params, who)

    @test()
    def test_case_maps_onto_the_editor(self, suite_parameter):
        s = self.seed()
        case = s["case"]
        out = self.load({"id": case["key"]})
        assert out["state"] == "default"
        c = out["data"]["case"]
        assert (c["id"], c["key"], c["title"], c["version"], c["feature"]) == (
            case["id"],
            case["key"],
            "Pay with a saved Visa card",
            1,
            s["card"]["id"],
        )
        assert (c["status"], c["priority"], c["type"], c["automation"], c["autoRef"]) == (
            "ready",
            "high",
            "functional",
            "manual",
            "",
        )
        assert c["tags"] == ["smoke"]
        assert c["links"] == [{"key": "PAY-2210", "url": "https://tracker.example.com/PAY-2210"}]
        assert c["desc"] == "A returning customer pays with a <b>saved</b> card."
        assert c["pre"] == "<ul><li>Stripe test mode</li><li>Visa ending 4242</li></ul>"
        stored = self.call("GET", f"/cases/{case['id']}")
        assert [st["id"] for st in c["steps"]] == [st["id"] for st in stored["steps"]]
        assert c["steps"][0]["action"] == "Open <b>Checkout</b>"
        assert c["steps"][0]["expected"] == "The summary shows <code>$42.00</code>"
        assert c["steps"][1]["action"] == "Press <i>Pay now</i>"
        assert c["src"] == {
            "desc": stored["description"],
            "pre": stored["preconditions"],
            "steps": {
                st["id"]: {"action": st["action"], "expected": st["expected"]} for st in stored["steps"]
            },
        }
        assert c["versions"] == [
            {"ver": "2.14.0", "status": "in_progress", "href": {"view": "releases", "id": s["release"]["id"]}}
        ]
        assert sorted(c["plans"], key=lambda p: p["name"]) == [
            {
                "name": "Checkout regression",
                "via": "feature",
                "href": {"view": "plans", "id": s["by_feature"]["id"]},
            },
            {"name": "Release smoke", "via": "case", "href": {"view": "plans", "id": s["by_case"]["id"]}},
        ]
        assert c["cycles"] == [
            {"name": "Checkout · staging", "pin": 1, "href": {"view": "cycles", "id": s["cycle"]["id"]}}
        ]
        version = self.call("GET", f"/cases/{case['id']}/versions/1")
        owner = next(
            a for a in self.call("GET", "/actors")["actors"] if a["id"] == version["created_by_actor_id"]
        )
        cur = c["current"]
        assert cur["by"] == {"kind": owner["kind"], "name": owner["name"]}
        assert (cur["onBehalf"], cur["via"], cur["openCycles"], cur["pins"]) == (
            "",
            version["via"] or "",
            1,
            [1],
        )
        assert cur["at"]
        d = out["data"]
        assert [f["v"] for f in d["folders"]] == [s["checkout"]["id"], s["card"]["id"], s["refunds"]["id"]]
        assert d["folders"][1] == {
            "v": s["card"]["id"],
            "label": "Checkout / Card payments",
            "name": "Card payments",
            "path": "Checkout › Card payments",
            "cases": 1,
        }
        assert d["tags"] == [{"v": "smoke", "cases": 1}]

    @test()
    def test_ui_states_come_from_the_hash_and_the_role(self, suite_parameter):
        s = self.seed()
        key = s["case"]["key"]
        md = self.load({"id": key, "ui": "markdown"})
        assert md["state"] == "markdown"
        served = self.call("GET", f"/cases/{s['case']['id']}/markdown")
        assert (md["data"]["case"]["md"], md["data"]["case"]["version"]) == (
            served["markdown"],
            served["version"],
        )
        assert "Pay with a saved Visa card" in served["markdown"]
        saved = self.load({"id": key, "ui": "saved"})
        assert (saved["state"], saved["data"]["savedAs"]) == ("saved", 1)
        support.add_member(self.live.owner, "vic@example.com", "viewer")
        viewer = self.load({"id": key, "ui": "markdown"}, who="vic@example.com")
        assert viewer["state"] == "viewer" and viewer["data"]["case"]["md"] == ""
        assert viewer["data"]["case"]["title"] == "Pay with a saved Visa card"

    @test()
    def test_no_id_is_a_new_case_in_the_asked_feature(self, suite_parameter):
        s = self.seed()
        out = self.load({"ui": "new-case", "feature": s["card"]["id"]})
        assert out["state"] == "new-case"
        c = out["data"]["case"]
        assert (c["id"], c["key"], c["feature"], c["status"], c["steps"]) == (
            "",
            "",
            s["card"]["id"],
            "draft",
            [{"id": "", "action": "", "expected": ""}],
        )
        assert c["pickedUpBy"] == [{"name": "Checkout regression", "ver": "2.14.0"}]
        first = self.load({"ui": "new-case"})["data"]["case"]
        assert first["feature"] == s["checkout"]["id"]
        refunds = self.load({"ui": "new-case", "feature": s["refunds"]["id"]})["data"]["case"]
        assert refunds["pickedUpBy"] == [{"name": "Refunds only", "ver": "any version"}]

    @test()
    def test_save_sends_the_edits_and_moves_the_case(self, suite_parameter):
        s = self.seed()
        case = s["case"]
        out = self.js(
            f"""const {{ data }} = await A.load(params, ctx);
            const c = data.case;
            const steps = c.steps.map((st) => ({{ id: st.id, action: null, expected: null }})).reverse();
            steps[0].expected = "Payment succeeds and a **receipt** is sent";
            steps.push({{ id: "", action: "Open *Orders*", expected: null }});
            return A.actions.save(c, {{
              title: "Pay with a saved card", desc: "Any saved card.", pre: null, steps,
              feature: {json.dumps(s["checkout"]["id"])}, status: "ready", priority: "critical",
              type: "regression", automation: "to_automate", autoRef: "tests/pay.py::Pay::test_saved",
              tags: ["smoke", "visa"], changeNote: "Reordered",
              links: [...c.links, {{ url: "https://tracker.example.com/PAY-2300", key: "" }}]
            }}, ctx);""",
            {"id": case["key"]},
        )
        assert (out["current_version"], out["feature_id"]) == (2, s["checkout"]["id"])
        got = self.call("GET", f"/cases/{case['id']}")
        assert (got["title"], got["description"], got["preconditions"]) == (
            "Pay with a saved card",
            "Any saved card.",
            "- Stripe test mode\n- Visa ending 4242",
        )
        assert [st["id"] for st in got["steps"][:2]] == [st["id"] for st in reversed(case["steps"])]
        assert got["steps"][0]["expected"] == "Payment succeeds and a **receipt** is sent"
        assert got["steps"][1]["expected"] == "The summary shows `$42.00`"
        assert (got["steps"][2]["action"], got["steps"][2]["expected"]) == ("Open *Orders*", "")
        assert (got["priority"], got["type"], got["automation"], got["automation_ref"]) == (
            "critical",
            "regression",
            "to_automate",
            "tests/pay.py::Pay::test_saved",
        )
        assert got["tags"] == ["smoke", "visa"] and got["change_note"] == "Reordered"
        assert got["links"] == [
            {"url": "https://tracker.example.com/PAY-2210", "key": "PAY-2210"},
            {"url": "https://tracker.example.com/PAY-2300", "key": None},
        ]
        assert got["feature_id"] == s["checkout"]["id"]

    @test()
    def test_save_markdown_puts_the_file_as_the_next_version(self, suite_parameter):
        s = self.seed()
        case = s["case"]
        out = self.js(
            """const { data } = await A.load(params, ctx);
            const md = data.case.md.replace("Pay with a saved Visa card", "Pay with a stored Visa card");
            return A.actions.saveMarkdown(data.case, md, "Renamed in Markdown", ctx);""",
            {"id": case["key"], "ui": "markdown"},
        )
        assert out["current_version"] == 2
        got = self.call("GET", f"/cases/{case['id']}")
        assert (got["title"], got["change_note"]) == ("Pay with a stored Visa card", "Renamed in Markdown")
        assert got["description"] == "A returning customer pays with a **saved** card."
        assert [st["id"] for st in got["steps"]] == [st["id"] for st in case["steps"]]

    @test()
    def test_create_makes_v1_in_the_feature(self, suite_parameter):
        s = self.seed()
        out = self.js(
            f"""return A.actions.create({{
              title: "Refund a whole order", desc: "Full refund.", pre: "",
              feature: {json.dumps(s["refunds"]["id"])},
              steps: [
                {{ id: "", action: "Open **Refunds**", expected: "The form opens" }},
                {{ id: "", action: null, expected: null }}
              ],
              status: "draft", priority: "medium", type: "functional", automation: "manual", autoRef: "",
              tags: ["smoke"], links: [], changeNote: ""
            }}, ctx);""",
            {"ui": "new-case"},
        )
        got = self.call("GET", f"/cases/{out['key']}")
        assert (got["id"], got["current_version"], got["feature_id"]) == (out["id"], 1, s["refunds"]["id"])
        assert (got["title"], got["description"], got["preconditions"], got["tags"]) == (
            "Refund a whole order",
            "Full refund.",
            "",
            ["smoke"],
        )
        assert [(st["action"], st["expected"]) for st in got["steps"]] == [
            ("Open **Refunds**", "The form opens")
        ]

    @test()
    def test_stale_save_is_the_raw_409(self, suite_parameter):
        s = self.seed()
        case = s["case"]
        self.call("PATCH", f"/cases/{case['id']}", {"title": "Changed elsewhere"}, headers={"If-Match": "1"})
        out = self.js(
            """const c = { id: params.id, version: 1, feature: "", steps: [], src: { steps: {} } };
            const edit = { title: "Mine", desc: null, pre: null, steps: [], feature: "", status: "ready",
              priority: "high", type: "functional", automation: "manual", autoRef: "", tags: [], links: [],
              changeNote: "" };
            return h.fail(A.actions.save(c, edit, ctx));""",
            {"id": case["id"]},
        )
        raw = self.live.owner.patch(
            f"{ORG}/cases/{case['id']}",
            json={
                "title": "Mine",
                "status": "ready",
                "priority": "high",
                "type": "functional",
                "automation": "manual",
                "automation_ref": None,
                "tags": [],
                "links": [],
                "change_note": None,
            },
            headers={"If-Match": "1"},
        )
        assert raw.status_code == 409, raw.text
        assert out == {"name": "ApiError", "status": 409, "raw": as_sent(raw)}
        assert self.call("GET", f"/cases/{case['id']}")["title"] == "Changed elsewhere"

    @test()
    def test_refused_step_is_raw_and_named(self, suite_parameter):
        s = self.seed()
        case = s["case"]
        bad = "Shows ![receipt](https://example.com/r.png)"
        out = self.js(
            f"""const {{ data }} = await A.load(params, ctx);
            const c = data.case;
            const steps = c.steps.map((st) => ({{ id: st.id, action: null, expected: null }}));
            steps[1].expected = {json.dumps(bad)};
            const edit = {{ title: c.title, desc: null, pre: null, steps, feature: c.feature,
              status: c.status, priority: c.priority, type: c.type, automation: c.automation, autoRef: "",
              tags: c.tags, links: c.links, changeNote: "" }};
            try {{ await A.actions.save(c, edit, ctx); return null; }}
            catch (e) {{ return {{ status: e.status, raw: A.raw(e), step: A.stepError(e) }}; }}""",
            {"id": case["key"]},
        )
        steps = [
            {"id": st["id"], "action": {"markdown": st["action"]}, "expected": {"markdown": st["expected"]}}
            for st in case["steps"]
        ]
        steps[1]["expected"] = {"markdown": bad}
        raw = self.live.owner.patch(
            f"{ORG}/cases/{case['id']}",
            json={
                "title": case["title"],
                "status": "ready",
                "priority": "high",
                "type": "functional",
                "automation": "manual",
                "automation_ref": None,
                "tags": ["smoke"],
                "links": [{"url": "https://tracker.example.com/PAY-2210", "key": "PAY-2210"}],
                "change_note": None,
                "steps": steps,
            },
            headers={"If-Match": "1"},
        )
        assert raw.status_code == 422, raw.text
        assert out == {"status": 422, "raw": as_sent(raw), "step": {"i": 1, "field": "expected"}}
        assert self.call("GET", f"/cases/{case['id']}")["current_version"] == 1
