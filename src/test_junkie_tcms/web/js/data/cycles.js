/* Cycles view data. Demo data only. */
const cycle = (name, release, env, kind, who, results, status, inBatch) => ({ name, release, env, assignee: { kind, name: who }, results, status, inBatch });
const cc = (key, title, pinned, newer, status, kind, who, hasResult, note, attempt) => ({ key, title, pinned, newer, status, assignee: { kind, name: who }, hasResult, note, attempt });

export default {
  base: {
    /* releases a cycle can target; released ones can't get new cycles */
    releases: [
      { ver: "2.14.0", name: "Spring checkout", status: "in_progress", date: "Fri Nov 27", features: 4 },
      { ver: "2.15.0", name: "Wallet upgrade", status: "planned", date: "Fri Dec 18", features: 2 },
      { ver: "2.16.0", name: "Payouts v2", status: "planned", date: "Fri Jan 22", features: 5 },
      { ver: "2.13.0", name: "Saved cards", status: "released", date: "Fri Oct 30", features: 0 },
      { ver: "2.12.0", name: "Refund webhooks", status: "released", date: "Fri Oct 9", features: 0 }
    ],
    /* environment labels already in use; kind picks the group */
    envs: [
      { v: "staging", label: "staging", hint: "staging.northwind.test", kind: "web" },
      { v: "prod-eu", label: "prod-eu", hint: "eu-west-1", kind: "web" },
      { v: "prod-us", label: "prod-us", hint: "us-east-1", kind: "web" },
      { v: "sandbox", label: "sandbox", hint: "Stripe test mode", kind: "web" },
      { v: "ios", label: "iPhone 15 / iOS 18", hint: "", kind: "device" },
      { v: "android", label: "Pixel 8 / Android 15", hint: "", kind: "device" }
    ],
    /* people (by handle) and agents a cycle or case can be assigned to */
    assignees: [
      { v: "lee", kind: "person", role: "tester", open: 6 },
      { v: "priya", kind: "person", short: "Priya Raman-C.", role: "tester", open: 2 },
      { v: "dana", kind: "person", role: "admin", open: null },
      { v: "ci", kind: "agent", name: "ci-reporter", note: "posts automated results" },
      { v: "nightly", kind: "agent", name: "nightly-smoke", note: "prod-eu only" }
    ],
    /* the product's feature tree, top level › feature */
    featureGroups: [
      { name: "Checkout", features: [{ v: "card", label: "Card payments", cases: 14, drafts: 1 }, { v: "wallet", label: "Apple Pay / Google Pay", cases: 9, drafts: 1 }, { v: "3ds", label: "3-D Secure challenge", cases: 8, drafts: 0 }] },
      { name: "Refunds", features: [{ v: "partial", label: "Partial refunds", cases: 12, drafts: 0 }, { v: "webhook", label: "refund_webhook_retry", cases: 6, drafts: 0 }] },
      { name: "Subscriptions", features: [{ v: "prorate", label: "Proration on plan change", cases: 12, drafts: 3 }] }
    ],
    tabs: { open: 6, closed: 14 },
    filter: { release: "2.14.0", env: "any", assignee: "any" },
    rows: [
      { kind: "batch", name: "Release 2.14.0 · bulk cycle", cycles: 4, by: "dana", on: "Thu Nov 12" },
      cycle("Checkout · Card payments", "2.14.0", "staging", "person", "lee", { success: 9, fail: 1, error: 1, ignore: 1, skip: 1, untested: 2 }, "open", true),
      cycle("Checkout · 3-D Secure challenge", "2.14.0", "staging", "person", "priya", { success: 3, ignore: 1, untested: 4 }, "open", true),
      cycle("Refunds · Partial refunds", "2.14.0", "staging", "agent", "ci-reporter", { success: 11, fail: 1 }, "open", true),
      cycle("Subscriptions · Proration on plan change", "2.14.0", "staging", "person", "lee", { untested: 12 }, "open", true),
      cycle("Smoke · nightly", "", "prod-eu", "agent", "nightly-smoke", { success: 17, skip: 2, cancel: 1 }, "open", false),
      cycle("Checkout · 2.13.0 · prod", "2.13.0", "prod", "person", "dana", { success: 30, fail: 1 }, "closed", false)
    ],
    /* the new-cycle form prefill and what the server says it would pin */
    draft: { name: "Checkout · wallets regression", features: ["card", "wallet"], release: "2.14.0", env: "staging", assignee: "lee", total: 23, ready: 21, drafts: 2, deprecated: 0, sample: { key: "PAY-101", ver: 7 } },
    /* the bulk cycle wizard */
    bulk: {
      release: "2.14.0", ready: 46, env: "staging", pattern: "{feature} · {release} · {env}", drafts: 4,
      features: [
        { path: "Checkout › Card payments", cases: 14, drafts: 1, assignee: "lee" },
        { path: "Checkout › 3-D Secure challenge", cases: 8, drafts: 0, assignee: "priya" },
        { path: "Refunds › Partial refunds", cases: 12, drafts: 0, assignee: "ci" },
        { path: "Subscriptions › Proration on plan change", cases: 12, drafts: 3, assignee: "lee" }
      ]
    },
    /* one cycle */
    cycle: {
      id: "c_8k2", name: "Checkout · Card payments", release: "2.14.0", env: "staging", status: "open",
      plan: "Checkout regression", planId: "pl_8k2", batch: "b_31", closedBy: "", closedAt: "",
      counts: { success: 9, fail: 1, error: 1, ignore: 1, skip: 1, untested: 2 },
      features: [{ path: "Checkout › Card payments", cases: 7 }, { path: "Checkout › Wallets", cases: 5 }, { path: "Checkout › 3-D Secure", cases: 3 }],
      cases: [
        cc("PAY-101", "Pay with a saved Visa card", 7, 8, "success", "person", "lee", true, "", 1),
        cc("PAY-102", "Card is declined with insufficient funds and the order stays unpaid", 3, 0, "fail", "agent", "ci-reporter", true, "PAY-JIRA-2291", 2),
        cc("PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", 2, 3, "untested", "person", "lee", false, "", 0),
        cc("PAY-140", "saved_card_token_expired_mid_session", 1, 0, "skip", "person", "priya", true, "Blocked by LAB-412: sandbox issuer down", 1),
        cc("PAY-141", "Card vault returns 500 while saving a card", 2, 0, "error", "agent", "ci-reporter", true, "Harness raised TimeoutError", 1),
        cc("PAY-143", "Legacy Maestro card flow", 4, 0, "ignore", "person", "lee", true, "Maestro sunset, ignored for 2.14.0", 1),
        cc("PAY-144", "Pay with a co-branded Visa debit card", 1, 0, "untested", "person", "lee", false, "", 0)
      ]
    },
    /* the version refresh the confirm dialog offers */
    refresh: { key: "PAY-118", from: 2, to: 3, step: "st_c81p", before: "Challenge window opens", after: "Challenge window opens within 3 s", tagsAdded: ["retry"] },
    error: ""
  },
  states: {
    "refresh-409": {
      error: `HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{"type":"https://test-junkie.dev/problems/cycle-case-has-results","title":"Conflict","status":409,"detail":"cycle_case cc_41x (PAY-118) has 1 result; version refresh is only allowed before the first result","request_id":"req_01JD3Q2X9P"}`
    },
    closed: { cycle: { status: "closed", closedBy: "dana", closedAt: "Fri Nov 13, 9:40 AM PT" } },
    empty: { rows: [], tabs: { open: 0, closed: 0 } }
  }
};
