/* MCP server view data. Demo data only. */
/* calls per range: the demo scales each tool's calls today by the range length */
const F = { today: 1, "7d": 6.8, "14d": 12.1, "30d": 23.4, custom: 7.3 };
const perRange = (today) => Object.fromEntries(Object.entries(F).map(([r, f]) => [r, Math.round(today * f)]));
/* kind: r read-only, i idempotent, d destructive, w write; tokCall ~tokens per call (p50 response), tokDef ~definition tokens */
const tool = (name, toolset, scope, desc, kind, tokCall, tokDef, today) => ({ name, toolset, scope, desc, kind, tokCall, tokDef, calls: perRange(today) });
/* one chart column: axis label, tooltip label and the calls in it; later() is a column of today still to come */
const col = (x, tip, reads, writes, errors) => ({ x, tip, reads, writes, errors });
const later = (x) => ({ x, later: true });
const update = (kind, icon, title, text, at) => ({ kind, icon, title, text, at });
const param = (arg, where, type, required, note) => ({ arg, where, type, required, note });
const call = (at, code, ms, tokens) => ({ at, code, ms, tokens, agent: "triage-bot", kind: "agent", actorId: "ag_triage" });

const TOOLS = [
  tool("products_list", "catalog", "read", "List the org's products (key, name).", "r", 380, 160, 42),
  tool("features_list", "catalog", "read", "The feature tree of a product.", "r", 1900, 180, 57),
  tool("features_create", "catalog", "write:catalog", "Add a feature under a parent.", "w", 260, 310, 1),
  tool("features_move", "catalog", "write:catalog", "Move a feature to a new parent or position.", "w", 240, 260, 0),
  tool("releases_list", "catalog", "read", "Releases of a product with status and target date.", "r", 640, 190, 22),
  tool("releases_set_features", "catalog", "write:catalog", "Set the features a release affects (PUT /releases/{id}/features).", "i", 300, 240, 0),
  tool("search", "catalog", "read", "Search cases, cycles and releases in the org.", "r", 1400, 170, 96),
  tool("cases_list", "cases", "read", "Cases filtered by feature, tag, q, status, automation.", "r", 2600, 290, 188),
  tool("cases_get", "cases", "read", "One case at its current version; rich fields as Markdown.", "r", 1100, 150, 312),
  tool("cases_create", "cases", "write:cases", "Create a case (version 1).", "w", 280, 690, 4),
  tool("cases_update", "cases", "write:cases", "Save a new version. expected_version (If-Match) is required; a stale one gets 409.", "w", 1100, 640, 37),
  tool("cases_versions_list", "cases", "read", "Versions of a case with author and change note.", "r", 700, 170, 15),
  tool("cases_version_get", "cases", "read", "One immutable version of a case.", "r", 1050, 180, 23),
  tool("cases_restore", "cases", "write:cases", "Copy version n into a new version.", "w", 300, 220, 0),
  tool("cases_archive", "cases", "write:cases", "Archive a case; versions and results are kept.", "d", 200, 170, 0),
  tool("cases_bulk_upsert", "cases", "write:cases", "Create or update many cases from Markdown in one call.", "w", 900, 720, 2),
  tool("exports_create", "cases", "read", "Export cases as csv or md-bundle (runs as a job).", "w", 210, 200, 1),
  tool("plans_list", "planning", "read", "Test plans of a product.", "r", 420, 160, 9),
  tool("plans_resolve", "planning", "read", "Preview the cases a plan resolves to.", "r", 1800, 190, 6),
  tool("cycles_list", "planning", "read", "Cycles with status, release and counts.", "r", 880, 200, 64),
  tool("cycles_create", "planning", "write:planning", "Start a cycle from a plan, features or cases.", "w", 340, 430, 3),
  tool("cycles_get", "planning", "read", "One cycle with pinned case versions and status counts.", "r", 1300, 150, 41),
  tool("cycles_bulk_create", "planning", "write:planning", "One cycle per affected feature of a release (POST /releases/{id}/cycles:bulk).", "w", 520, 380, 1),
  tool("cycle_cases_list", "planning", "read", "Cases in a cycle with pinned version, assignee and status.", "r", 2400, 240, 133),
  tool("cycle_cases_refresh_version", "planning", "write:planning", "Move a cycle case to the current case version, only before its first result.", "w", 260, 230, 2),
  tool("results_create", "execution", "write:execution", "Record a result: success, fail, error, ignore, skip or cancel.", "w", 300, 560, 88),
  tool("results_list", "execution", "read", "Result attempts of a cycle case.", "r", 760, 170, 27),
  tool("results_bulk_create", "execution", "write:execution", "Many results by case key or automation_ref (POST /cycles/{id}/results:bulk).", "w", 420, 610, 12),
  tool("attachments_upload_base64", "execution", "write:execution", "Evidence as base64 JSON, capped at 5 MB. MCP's stand-in for the multipart upload.", "w", 180, 260, 9),
  tool("reports_release", "reports", "read", "Release readiness per feature, against the case version.", "r", 1600, 180, 19),
  tool("reports_feature", "reports", "read", "Results for one feature across cycles.", "r", 1200, 160, 7),
  tool("reports_cycle", "reports", "read", "Status counts and progress of one cycle.", "r", 900, 150, 14),
  tool("audit_list", "admin", "audit:read", "Audit events by entity, actor and since.", "r", 2200, 220, 0),
  tool("agents_list", "admin", "admin", "Agents with owner, role and status.", "r", 520, 150, 0),
  tool("tokens_list", "admin", "admin", "Tokens (prefix only, never the secret).", "r", 610, 150, 0),
  tool("members_list", "admin", "read", "Members and their roles.", "r", 680, 150, 0),
  tool("orgs_get", "admin", "read", "The org and its settings.", "r", 300, 140, 0)
];
const UPDATES = [
  update("acc", "spark", "Server v1.0.0 started", "Official mcp Python SDK, version pinned in the scaffold plan. 32 tools in the default toolsets.", "Sat Nov 14, 9:12 AM PT"),
  update("info", "plus", "Tool list changed: +cycle_cases_refresh_version", "Connected clients were sent notifications/tools/list_changed.", "Fri Nov 13, 4:40 PM PT"),
  update("info", "build", "Schema changed: cases_update", "expected_version (If-Match) is now a required arg; idempotency_key added on every POST tool.", "Wed Nov 11, 2:15 PM PT")
];

export default {
  base: {
    range: "today",
    loading: false,
    zone: "PT",
    server: { up: true, version: "1.0.0" },
    apiOps: 70,
    toolsets: ["catalog", "cases", "planning", "execution", "reports", "admin"],
    tools: TOOLS,
    /* per range: the chart columns, the column that is now (-1: none) and the totals */
    ranges: {
      today: { now: 14, totals: { calls: 1236, errors: 24, tokens: 1735324, clients: 3 }, columns: [
        col("12a", "Sat Nov 14 · 12:00 AM–1:00 AM PT", 11, 4, 0),
        col("", "Sat Nov 14 · 1:00 AM–2:00 AM PT", 13, 4, 1),
        col("", "Sat Nov 14 · 2:00 AM–3:00 AM PT", 44, 14, 1),
        col("3a", "Sat Nov 14 · 3:00 AM–4:00 AM PT", 13, 4, 0),
        col("", "Sat Nov 14 · 4:00 AM–5:00 AM PT", 11, 4, 0),
        col("", "Sat Nov 14 · 5:00 AM–6:00 AM PT", 10, 3, 0),
        col("6a", "Sat Nov 14 · 6:00 AM–7:00 AM PT", 13, 4, 0),
        col("", "Sat Nov 14 · 7:00 AM–8:00 AM PT", 39, 13, 1),
        col("", "Sat Nov 14 · 8:00 AM–9:00 AM PT", 66, 21, 1),
        col("9a", "Sat Nov 14 · 9:00 AM–10:00 AM PT", 113, 37, 5),
        col("", "Sat Nov 14 · 10:00 AM–11:00 AM PT", 99, 32, 2),
        col("", "Sat Nov 14 · 11:00 AM–12:00 PM PT", 135, 44, 3),
        col("12p", "Sat Nov 14 · 12:00 PM–1:00 PM PT", 154, 50, 3),
        col("", "Sat Nov 14 · 1:00 PM–2:00 PM PT", 113, 37, 5),
        col("", "Sat Nov 14 · 2:00 PM–3:00 PM PT", 81, 26, 2),
        later("3p"), later(""), later(""), later("6p"), later(""), later(""), later("9p"), later(""), later("")
      ] },
      "7d": { now: 6, totals: { calls: 8406, errors: 177, tokens: 11801888, clients: 4 }, columns: [
        col("Sun 8", "Sun Nov 8", 470, 152, 10),
        col("Mon 9", "Mon Nov 9", 1463, 474, 59),
        col("Tue 10", "Tue Nov 10", 798, 259, 16),
        col("Wed 11", "Wed Nov 11", 886, 287, 18),
        col("Thu 12", "Thu Nov 12", 1210, 392, 25),
        col("Fri 13", "Fri Nov 13", 1046, 339, 42),
        col("Sat 14", "Sat Nov 14", 342, 111, 7)
      ] },
      "14d": { now: 13, totals: { calls: 14944, errors: 299, tokens: 20981134, clients: 4 }, columns: [
        col("Nov 1", "Nov 1", 416, 135, 8),
        col("", "Nov 2", 1294, 420, 52),
        col("Nov 3", "Nov 3", 707, 229, 14),
        col("", "Nov 4", 784, 254, 16),
        col("Nov 5", "Nov 5", 1070, 347, 22),
        col("", "Nov 6", 925, 300, 38),
        col("Nov 7", "Nov 7", 302, 98, 6),
        col("", "Nov 8", 258, 84, 5),
        col("Nov 9", "Nov 9", 1024, 332, 21),
        col("", "Nov 10", 1181, 383, 48),
        col("Nov 11", "Nov 11", 595, 193, 12),
        col("", "Nov 12", 911, 295, 18),
        col("Nov 13", "Nov 13", 1271, 412, 26),
        col("", "Nov 14", 321, 104, 13)
      ] },
      "30d": { now: 29, totals: { calls: 28868, errors: 550, tokens: 40530205, clients: 4 }, columns: [
        col("Oct 16", "Oct 16", 388, 126, 8),
        col("", "Oct 17", 1208, 392, 49),
        col("", "Oct 18", 660, 214, 13),
        col("", "Oct 19", 732, 237, 15),
        col("", "Oct 20", 999, 324, 20),
        col("Oct 21", "Oct 21", 864, 280, 35),
        col("", "Oct 22", 282, 91, 6),
        col("", "Oct 23", 241, 78, 5),
        col("", "Oct 24", 957, 310, 19),
        col("", "Oct 25", 1103, 358, 45),
        col("Oct 26", "Oct 26", 556, 180, 11),
        col("", "Oct 27", 850, 276, 17),
        col("", "Oct 28", 1187, 385, 24),
        col("", "Oct 29", 300, 97, 12),
        col("", "Oct 30", 207, 67, 4),
        col("Oct 31", "Oct 31", 942, 306, 19),
        col("", "Nov 1", 895, 290, 18),
        col("", "Nov 2", 864, 280, 35),
        col("", "Nov 3", 636, 206, 13),
        col("", "Nov 4", 969, 314, 20),
        col("Nov 5", "Nov 5", 581, 188, 12),
        col("", "Nov 6", 164, 53, 7),
        col("", "Nov 7", 841, 273, 17),
        col("", "Nov 8", 1157, 375, 23),
        col("", "Nov 9", 714, 232, 14),
        col("Nov 10", "Nov 10", 742, 241, 30),
        col("", "Nov 11", 884, 287, 18),
        col("", "Nov 12", 515, 167, 10),
        col("", "Nov 13", 344, 112, 7),
        col("", "Nov 14", 602, 195, 24)
      ] },
      custom: { now: -1, totals: { calls: 9024, errors: 187, tokens: 12669550, clients: 2 }, columns: [
        col("Nov 2", "Nov 2", 482, 156, 10),
        col("Nov 3", "Nov 3", 1501, 487, 61),
        col("Nov 4", "Nov 4", 819, 266, 17),
        col("Nov 5", "Nov 5", 909, 295, 18),
        col("Nov 6", "Nov 6", 1241, 402, 25),
        col("Nov 7", "Nov 7", 1072, 348, 43),
        col("Nov 8", "Nov 8", 350, 114, 7),
        col("Nov 9", "Nov 9", 298, 97, 6)
      ] }
    },
    errorsMostly: "409 stale version",
    clientNames: ["triage-bot", "ci-reporter", "Dana's CLI"],
    /* the latest call: the tool name only (its arguments are not stored) */
    lastCall: { call: "cases_get", agent: "triage-bot", kind: "agent", actorId: "ag_triage", code: 200, ms: 84, tokens: 1100, at: "just now" },
    connect: { base: "https://tcms.northwind.test" },
    updates: UPDATES,
    /* what live mode polls (data/mcp.js poll); the render test never polls */
    live: null,
    /* the tool open in the detail drawer */
    detail: {
      tool: "cases_update", path: "/api/v1/cases/{key}", errorsToday: 2, p95: 3400,
      params: [
        param("key", "path", "string", true, "PAY-101"),
        param("expected_version", "header If-Match", "integer", true, "stale → 409 with current_version"),
        param("title", "body", "string", false, ""),
        param("preconditions", "body", "Markdown", false, "rich field"),
        param("steps", "body", "array of {id, action, expected}", false, "action and expected are Markdown; ids stay stable"),
        param("priority", "body", "string", false, ""),
        param("tags", "body", "string[]", false, ""),
        param("change_note", "body", "string", false, "shown in version history")
      ],
      /* status, latency and size only: a call's arguments and response body are not stored */
      calls: [
        call("3:14 PM", 200, 212, 1200),
        call("3:13 PM", 409, 48, 200),
        call("11:02 AM", 200, 190, 1100),
        call("9:47 AM", 200, 176, 900),
        call("Fri 4:20 PM", 422, 31, 300)
      ],
      /* a write: its calls are audited */
      audited: true
    }
  },
  states: {
    "7d": { range: "7d" },
    "14d": { range: "14d" },
    "30d": { range: "30d" },
    "custom-open": { range: "7d", picker: { value: "custom", open: true } },
    "custom-applied": { range: "custom", picker: { value: "custom", applied: true, from: "2026-11-02", to: "2026-11-09" }, lastCall: { at: "Mon Nov 9, 6:41 PM PT" } },
    empty: {
      ranges: { today: { totals: { calls: 0, errors: 0, tokens: 0, clients: 0 } } },
      tools: TOOLS.map((t) => ({ ...t, calls: perRange(0) })),
      updates: UPDATES.slice(0, 1)
    },
    offline: {
      server: { up: false },
      offline: { error: "connect ECONNREFUSED 127.0.0.1:8000", lastData: "Sat Nov 14, 2:12 PM PT", lastKnownCalls: 1071, lastKnownAt: "2:12 PM PT" }
    },
    loading: { loading: true }
  }
};
