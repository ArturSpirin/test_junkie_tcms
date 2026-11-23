/* Audit log view data. Demo data only. */
/* actor is { kind, id }: kind person (id = handle), agent, token or system; onBehalfOf is a person's handle */
const ev = (day, time, actor, token, onBehalfOf, via, action, type, id, version, summary, detail) => ({ day, time, actor, token, onBehalfOf, via, action, type, id, version, summary, ...(detail ? { detail } : {}) });
const person = (id) => ({ kind: "person", id });
const agent = (id) => ({ kind: "agent", id });

const EVENTS = [
  ev("Fri Nov 13", "10:05 AM PT", person("dana"), "", "", "ui", "cases.restore", "case", "PAY-101", 8, "Restored v5 as v8"),
  ev("Fri Nov 13", "2:05 AM PT", agent("ci-reporter"), "tjt_8f3k2a1q", "", "reporter", "results.create", "cycle_case", "PAY-102", 3, "success · Smoke · nightly"),
  ev("Thu Nov 12", "4:20 PM PT", person("lee"), "", "", "ui", "results.create", "cycle_case", "PAY-101", 7, "fail · step 3 · LAB-418"),
  ev("Thu Nov 12", "3:14 PM PT", agent("triage-bot"), "tjt_q7m2c9xd", "dana", "mcp", "cases.update", "case", "PAY-101", 7, "steps reordered, expected changed, tag visa", {
    at: "2026-11-12T15:14:07-08:00", requestId: "req_01JD6QW8T3BN", tool: "cases_update",
    changes: [
      { field: "steps[st_2m8x].position", before: 4, after: 3 },
      { field: "steps[st_2m8x].expected", before: "Payment succeeds and order status is paid", after: "Payment succeeds: order status is paid; a receipt email is queued" },
      { field: "tags", before: ["smoke"], after: ["smoke", "visa"] }
    ]
  }),
  ev("Thu Nov 12", "11:40 AM PT", person("dana"), "", "", "ui", "cycles.bulk_create", "release", "2.14.0", 0, "4 cycles, one per affected feature"),
  ev("Thu Nov 12", "9:02 AM PT", { kind: "token", id: "tjt_3n5wv0ke" }, "tjt_3n5wv0ke", "dana", "api", "cases.import", "feature", "Refunds › refund_webhook_retry", 0, "6 cases from CSV"),
  ev("Wed Nov 11", "5:30 PM PT", person("dana"), "", "", "ui", "tokens.create", "token", "tjt_q7m2c9xd", 0, "owner triage-bot · read, write:cases, write:planning"),
  ev("Wed Nov 11", "5:28 PM PT", person("dana"), "", "", "ui", "agents.create", "agent", "triage-bot", 0, "role editor"),
  ev("Wed Nov 11", "3:00 AM PT", { kind: "system", id: "system" }, "", "", "system", "cycle_cases.refresh", "cycle_case", "PAY-107", 4, "v3 → v4 before first result")
];
const BY_AGENT = EVENTS.filter((e) => e.actor.id === "triage-bot" || e.id === "triage-bot" || e.id === "tjt_q7m2c9xd");
const BY_CASE = EVENTS.filter((e) => e.id === "PAY-101").concat([
  ev("Tue Nov 10", "11:02 AM PT", person("lee"), "", "", "ui", "cases.update", "case", "PAY-101", 6, "Added receipt email check"),
  ev("Tue Oct 20", "10:12 AM PT", person("dana"), "", "", "ui", "cases.create", "case", "PAY-101", 1, "Created")
]);

export default {
  base: {
    retention: { days: 90, oldest: "Sat Aug 15" },
    /* the actor filter's choices beyond the fixed kinds */
    agents: [{ id: "triage-bot", owner: "dana", role: "editor" }, { id: "ci-reporter", owner: "lee", role: "tester" }],
    members: [{ handle: "dana", role: "admin" }, { handle: "lee", role: "editor" }, { handle: "priya", role: "tester" }],
    /* filter values; range is the date range (from is an ISO date, to defaults to today) */
    filter: { actor: "any", action: "any", via: "any", type: "any", entityId: "", viaOpen: false, range: { value: "7d" } },
    events: EVENTS,
    /* index of the expanded event, -1 for none */
    open: -1,
    entity: null
  },
  states: {
    "filter-open": { filter: { viaOpen: true } },
    "filtered-agent": { filter: { actor: "agent:triage-bot" }, events: BY_AGENT },
    expanded: { open: EVENTS.findIndex((e) => e.actor.id === "triage-bot") },
    entity: {
      entity: { type: "case", id: "PAY-101", title: "Pay with a saved Visa card" },
      filter: { type: "case", entityId: "PAY-101", range: { value: "30d" } },
      events: BY_CASE
    },
    empty: { filter: { actor: "agent:triage-bot", range: { value: "today" } }, events: [] },
    retention: { filter: { range: { value: "custom", applied: true, from: "2026-08-15" } }, events: EVENTS.slice(-2) }
  }
};
