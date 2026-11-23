/* Audit log view data. Demo data only, in the shape web/js/data/audit.js gives. */
/* actor is { kind, id, name }: kind person (id = actor id), agent, token or consumer; onBehalfOf is a person's actor id */
let n = 0;
const ev = (day, time, actor, token, onBehalfOf, via, action, type, id, version, summary, detail) => ({
  eid: `ev_${++n}`, day, time, actor, token, onBehalfOf, via, action, type, id, entityId: id, version, summary,
  detail: detail || { at: "", requestId: "", tool: "", changes: [] }, raw: { id: `ev_${n}`, action }
});
const person = (id) => ({ kind: "person", id, name: id });
const agent = (id) => ({ kind: "agent", id: "a_" + id, name: id });

const EVENTS = [
  ev("Fri Nov 13", "10:05 AM PT", person("dana"), "", "", "ui", "case.restore", "case", "PAY-101", 8, "Restored v5 as v8"),
  ev("Fri Nov 13", "2:05 AM PT", agent("ci-reporter"), "tjt_8f3k2a1q", "", "api", "result.create", "cycle_case", "PAY-102", 3, "success · Smoke · nightly"),
  ev("Thu Nov 12", "4:20 PM PT", person("lee"), "", "", "ui", "result.create", "cycle_case", "PAY-101", 7, "fail · step 3 · LAB-418"),
  ev("Thu Nov 12", "3:14 PM PT", agent("triage-bot"), "tjt_q7m2c9xd", "dana", "mcp", "case.update", "case", "PAY-101", 7, "steps reordered, expected changed, tag visa", {
    at: "2026-11-12T15:14:07-08:00", requestId: "req_01JD6QW8T3BN", tool: "cases_update",
    changes: [
      { field: "steps[st_2m8x].position", before: 4, after: 3 },
      { field: "steps[st_2m8x].expected", before: "Payment succeeds and order status is paid", after: "Payment succeeds: order status is paid; a receipt email is queued" },
      { field: "tags", before: ["smoke"], after: ["smoke", "visa"] }
    ]
  }),
  ev("Thu Nov 12", "11:40 AM PT", person("dana"), "", "", "ui", "cycle_batch.create", "release", "2.14.0", 0, "4 cycles, one per affected feature"),
  ev("Thu Nov 12", "9:02 AM PT", person("dana"), "tjt_3n5wv0ke", "", "api", "case.import", "feature", "Refunds › refund_webhook_retry", 0, "6 cases from CSV"),
  ev("Wed Nov 11", "5:30 PM PT", person("dana"), "", "", "ui", "token.create", "token", "tjt_q7m2c9xd", 0, "owner triage-bot · read, write:cases, write:planning"),
  ev("Wed Nov 11", "5:28 PM PT", person("dana"), "", "", "ui", "agent.create", "agent", "triage-bot", 0, "role editor"),
  ev("Wed Nov 11", "3:00 AM PT", { kind: "consumer", id: "c_7f2", name: "QA lab Mac mini" }, "", "", "api", "cycle_case.refresh_version", "cycle_case", "PAY-107", 4, "v3 → v4 before first result")
];
const BY_AGENT = EVENTS.filter((e) => e.actor.name === "triage-bot" || e.id === "triage-bot" || e.id === "tjt_q7m2c9xd");
const BY_CASE = EVENTS.filter((e) => e.id === "PAY-101").concat([
  ev("Tue Nov 10", "11:02 AM PT", person("lee"), "", "", "ui", "case.update", "case", "PAY-101", 6, "Added receipt email check"),
  ev("Tue Oct 20", "10:12 AM PT", person("dana"), "", "", "ui", "case.create", "case", "PAY-101", 1, "Created")
]);

export default {
  base: {
    retention: { days: 90, oldest: "Sat Aug 15", oldestDay: "2026-08-15" },
    /* the actor filter's choices beyond the fixed kinds */
    agents: [{ id: "a_triage-bot", name: "triage-bot", owner: "dana", role: "editor" }, { id: "a_ci-reporter", name: "ci-reporter", owner: "lee", role: "tester" }],
    members: [{ handle: "dana", role: "admin" }, { handle: "lee", role: "editor" }, { handle: "priya", role: "tester" }],
    /* filter values; range is the date range (from is an ISO date, to defaults to today) */
    filter: { actor: "any", actorLabel: "any", action: "any", via: "any", type: "any", entityId: "", entityLabel: "", q: "", viaOpen: false, range: { value: "7d" } },
    events: EVENTS,
    /* every event the filters match, across pages */
    total: EVENTS.length,
    /* index of the expanded event, -1 for none */
    open: -1,
    entity: null
  },
  states: {
    "filter-open": { filter: { viaOpen: true } },
    "filtered-agent": { filter: { actor: "agent:a_triage-bot", actorLabel: "triage-bot" }, events: BY_AGENT, total: BY_AGENT.length },
    expanded: { open: EVENTS.findIndex((e) => e.actor.name === "triage-bot") },
    entity: {
      entity: { type: "case", id: "PAY-101", key: "PAY-101", title: "Pay with a saved Visa card" },
      filter: { type: "case", entityId: "c_101", entityLabel: "PAY-101", range: { value: "30d" } },
      events: BY_CASE, total: BY_CASE.length
    },
    empty: { filter: { actor: "agent:a_triage-bot", actorLabel: "triage-bot", range: { value: "today" } }, events: [], total: 0 },
    retention: { filter: { range: { value: "custom", applied: true, from: "2026-08-15" } }, events: EVENTS.slice(-2), total: 2 }
  }
};
