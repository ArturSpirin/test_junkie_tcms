/* Cycles view data, in the shape data/cycles.js gives. Demo data only. */
const cycle = (id, name, release, env, kind, who, results, status, inBatch) => ({ id, name, release, env, assignee: { kind, name: who }, results, status, inBatch });
const cc = (id, key, title, pinned, newer, status, kind, who, hasResult, note, attempt) => ({ id, key, title, pinned, newer, status, assignee: { kind, name: who }, hasResult, note, attempt });

export default {
  base: {
    product: { id: "p_pay", key: "PAY", name: "Payments" },
    /* releases a cycle can target; released ones can't get new cycles */
    releases: [
      { id: "r_214", ver: "2.14.0", name: "Spring checkout", status: "in_progress", date: "Fri Nov 27", features: 4 },
      { id: "r_215", ver: "2.15.0", name: "Wallet upgrade", status: "planned", date: "Fri Dec 18", features: 2 },
      { id: "r_216", ver: "2.16.0", name: "Payouts v2", status: "planned", date: "Fri Jan 22", features: 5 },
      { id: "r_213", ver: "2.13.0", name: "Saved cards", status: "released", date: "Fri Oct 30", features: 0 },
      { id: "r_212", ver: "2.12.0", name: "Refund webhooks", status: "released", date: "Fri Oct 9", features: 0 }
    ],
    /* environment labels the listed cycles use (a free label) */
    envs: [
      { v: "staging", label: "staging", hint: "" },
      { v: "prod-eu", label: "prod-eu", hint: "" },
      { v: "prod", label: "prod", hint: "" }
    ],
    /* people (by actor id) and agents a cycle or case can be assigned to */
    assignees: [
      { v: "lee", kind: "person", role: "tester" },
      { v: "priya", kind: "person", role: "tester" },
      { v: "dana", kind: "person", role: "admin" },
      { v: "ci", kind: "agent", name: "ci-reporter" },
      { v: "nightly", kind: "agent", name: "nightly-smoke" }
    ],
    /* the product's feature tree, one group per top-level feature */
    featureGroups: [
      { name: "Checkout", features: [{ v: "f_co", label: "Checkout", cases: 31 }, { v: "card", label: "Checkout › Card payments", cases: 14 }, { v: "wallet", label: "Checkout › Apple Pay / Google Pay", cases: 9 }, { v: "3ds", label: "Checkout › 3-D Secure challenge", cases: 8 }] },
      { name: "Refunds", features: [{ v: "f_rf", label: "Refunds", cases: 18 }, { v: "partial", label: "Refunds › Partial refunds", cases: 12 }, { v: "webhook", label: "Refunds › refund_webhook_retry", cases: 6 }] }
    ],
    tabs: { open: 6, closed: 14 },
    filter: { status: "open", release: "any", env: "any", assignee: "any" },
    rows: [
      { kind: "batch", id: "b_31", name: "2.14.0", per: "features", cycles: 4, on: "Thu Nov 12", by: { kind: "person", name: "dana" }, closedBy: null },
      cycle("c_8k2", "2.14.0 · Card payments", "2.14.0", "staging", "person", "lee", { success: 9, fail: 1, error: 1, ignore: 1, skip: 1, untested: 2 }, "open", true),
      cycle("c_8k3", "2.14.0 · 3-D Secure challenge", "2.14.0", "staging", "person", "priya", { success: 3, ignore: 1, untested: 4 }, "open", true),
      cycle("c_8k4", "2.14.0 · Partial refunds", "2.14.0", "staging", "agent", "ci-reporter", { success: 11, fail: 1 }, "open", true),
      cycle("c_8k5", "2.14.0 · Proration on plan change", "2.14.0", "staging", "person", "lee", { untested: 12 }, "open", true),
      cycle("c_8k6", "Smoke · nightly", "", "prod-eu", "agent", "nightly-smoke", { success: 17, skip: 2, cancel: 1 }, "open", false),
      cycle("c_7z1", "Checkout · 2.13.0 · prod", "2.13.0", "prod", "person", "dana", { success: 30, fail: 1 }, "closed", false)
    ],
    /* the new-cycle form prefill and what the server says it would pin */
    draft: { name: "Checkout · wallets regression", features: ["card", "wallet"], release: "2.14.0", env: "staging", assignee: "lee", total: 23, deprecated: 0, archived: 0, drafts: 2 },
    /* the bulk cycle wizard: one row per affected feature, its cases with drafts left out and the drafts skipped */
    bulk: {
      release: "2.14.0", releaseId: "r_214", env: "staging", per: "features", plans: 1, featureCount: 4, cases: 49, total: 46, drafts: 3,
      pattern: "{release} · {feature}",
      features: [
        { id: "card", path: "Checkout › Card payments", cases: 14, drafts: 2, assignee: "lee" },
        { id: "3ds", path: "Checkout › 3-D Secure challenge", cases: 8, drafts: 0, assignee: "priya" },
        { id: "partial", path: "Refunds › Partial refunds", cases: 12, drafts: 1, assignee: "ci" },
        { id: "proration", path: "Subscriptions › Proration on plan change", cases: 12, drafts: 0, assignee: "none" }
      ]
    },
    /* one cycle */
    cycle: {
      id: "c_8k2", name: "2.14.0 · Card payments", release: "2.14.0", releaseId: "r_214", env: "staging", status: "open",
      plan: "Checkout regression", planId: "pl_8k2", batch: "b_31", closedAt: "", closedBy: null,
      counts: { success: 1, fail: 1, error: 1, ignore: 1, skip: 1, cancel: 0, untested: 2 },
      features: [{ id: "card", path: "Checkout › Card payments", cases: 7 }],
      cases: [
        cc("cc_1", "PAY-101", "Pay with a saved Visa card", 7, 8, "success", "person", "lee", true, "", 1),
        cc("cc_2", "PAY-102", "Card is declined with insufficient funds and the order stays unpaid", 3, 0, "fail", "agent", "ci-reporter", true, "PAY-JIRA-2291", 2),
        cc("cc_3", "PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", 2, 3, "untested", "person", "lee", false, "", 0),
        cc("cc_4", "PAY-140", "saved_card_token_expired_mid_session", 1, 0, "skip", "person", "priya", true, "Blocked by LAB-412: sandbox issuer down", 1),
        cc("cc_5", "PAY-141", "Card vault returns 500 while saving a card", 2, 0, "error", "agent", "ci-reporter", true, "Harness raised TimeoutError", 1),
        cc("cc_6", "PAY-143", "Legacy Maestro card flow", 4, 0, "ignore", "person", "lee", true, "Maestro sunset, ignored for 2.14.0", 1),
        cc("cc_7", "PAY-144", "Pay with a co-branded Visa debit card", 1, 0, "untested", "person", "lee", false, "", 0)
      ]
    },
    /* the version refresh the confirm dialog offers */
    refresh: { id: "cc_3", key: "PAY-118", from: 2, to: 3, results: 0, step: "st_c81p", before: "Challenge window opens", after: "Challenge window opens within 3 s", tagsAdded: ["retry"] },
    error: ""
  },
  states: {
    "refresh-409": {
      error: `HTTP/1.1 409 Conflict\nContent-Type: application/problem+json\n\n{"type":"about:blank","title":"Conflict","status":409,"detail":"The cycle is closed; reopen it first","code":"cycle_closed"}`
    },
    closed: { cycle: { status: "closed", closedAt: "Fri Nov 13, 9:40 AM", closedBy: { kind: "person", name: "dana" } } },
    empty: { rows: [], tabs: { open: 0, closed: 0 } }
  }
};
