/* Tokens and agents view data, in data/tokens.js's shape. Demo data only. */
const token = (id, name, prefix, kind, owner, scopes, products, lastUsed, expires, status) => ({ id, name, prefix, owner: { kind, handle: owner }, scopes, products, lastUsed, expires, status });
const agent = (id, name, desc, owner, role, tokens, lastActive, status) => ({ id, name, desc, owner, role, tokens, lastActive, status });

const CI = ["tok_ci", "CI reporter, payments", "tjt_8f3k2a1q", "agent", "ci-reporter", ["read", "write:execution"], ["PAY", "MOB"], "Fri Nov 13, 2:05 AM PT", "Fri Feb 12, 2027"];
const REST = [
  token("tok_triage", "triage-bot MCP", "tjt_q7m2c9xd", "agent", "triage-bot", ["read", "write:cases", "write:planning"], [], "Thu Nov 12, 3:14 PM PT", "Sun Nov 22", "expiring"),
  token("tok_dana", "Dana · local scripts", "tjt_3n5wv0ke", "person", "dana", ["read", "audit:read"], [], "Tue Nov 10, 9:00 AM PT", "never", "active")
];
const JENKINS = token("tok_jenkins", "old jenkins", "tjt_z1p8r4ta", "person", "lee", ["read", "write:execution"], ["PAY"], "Mon Sep 14, 11:30 PM PT", "–", "revoked");
const CIREP = agent("agt_ci", "ci-reporter", "Posts pytest results from CI with the Test Junkie reporter.", "lee", "tester", 1, "Fri Nov 13, 2:05 AM PT", "active");
const TRIAGE = (status) => agent("agt_triage", "triage-bot", "Reads failed results and drafts case edits through MCP.", "dana", "editor", 1, "Fri Nov 13, 3:14 PM PT", status);

export default {
  base: {
    baseUrl: "https://tcms.northwind.test",
    /* the role the signed-in user acts with on this screen; null = the user's org role */
    roleAs: null,
    scopes: [
      { scope: "read", desc: "Read catalog, cycles, results, reports" },
      { scope: "write:catalog", desc: "Products, features, releases, tags" },
      { scope: "write:planning", desc: "Test plans and cycles" },
      { scope: "write:cases", desc: "Create and edit cases (new versions)" },
      { scope: "write:execution", desc: "Record results, evidence, defects" },
      { scope: "audit:read", desc: "Read the audit log" },
      { scope: "admin", desc: "Members, roles, org settings" },
      { scope: "tokens:self", desc: "Manage this user's own tokens" }
    ],
    /* scopes each role may grant; admin may grant every scope */
    roleScopes: {
      viewer: ["read", "tokens:self"],
      tester: ["read", "write:execution", "tokens:self"],
      editor: ["read", "write:execution", "write:cases", "write:planning", "tokens:self"],
      admin: ["read", "write:catalog", "write:planning", "write:cases", "write:execution", "audit:read", "admin", "tokens:self"],
      owner: ["read", "write:catalog", "write:planning", "write:cases", "write:execution", "audit:read", "admin", "tokens:self"]
    },
    tokens: [token(...CI, "active"), ...REST, JENKINS],
    agents: [TRIAGE("active"), CIREP],
    /* products a token can be limited to */
    products: [{ key: "PAY", name: "Payments", markCls: "" }, { key: "MOB", name: "Mobile app", markCls: "b" }, { key: "WEB", name: "Storefront", markCls: "c" }],
    /* expiry choice (days) → the date it lands on */
    expiryDates: { 7: "Sat Nov 21", 30: "Mon Dec 14", 90: "Thu Feb 11, 2027", 365: "Sun Nov 14, 2027" },
    draft: { name: "Nightly pytest reporter", owner: "me", on: ["read", "write:execution"], products: ["PAY", "MOB"], expiry: "90" },
    /* people who can own an agent, with their org role */
    owners: [{ handle: "lee", userId: "u_lee", role: "editor" }, { handle: "dana", userId: "u_dana", role: "admin" }, { handle: "priya", userId: "u_priya", role: "tester" }],
    agentDraft: { name: "release-notes-bot", owner: "lee", desc: "Drafts release notes from closed 2.14.0 cycles.", role: "tester" },
    created: { secret: "tjt_x4b7h2no_Yq3vM9kTzP0wLr8sJd2fNc6eHa1uGi5o", prefix: "tjt_x4b7h2no", scopes: ["read", "write:execution"], products: ["PAY", "MOB"], expires: "Thu Feb 11, 2027" },
    /* the token id for revoke-confirm, the agent id just disabled for agent-disabled */
    revoke: "tok_ci",
    disabled: null,
    ownerOpen: false,
    self: null,
    error: null
  },
  states: {
    create: { roleAs: "editor" },
    "create-owner-open": { ownerOpen: true },
    revoked: { tokens: [token(...CI, "revoked"), ...REST, JENKINS] },
    "agent-disabled": { agents: [TRIAGE("disabled"), CIREP], disabled: "agt_triage" },
    "self-only": {
      roleAs: "tester",
      self: "lee",
      tokens: [token("tok_lee", "Lee · laptop", "tjt_m0d4s1ua", "person", "lee", ["read", "write:execution"], ["PAY"], "Thu Nov 12, 6:12 PM PT", "Wed Feb 10, 2027", "active"), JENKINS]
    },
    "error-422": {
      error: {
        owner: "ci-reporter", ownerRole: "tester", on: ["read", "write:execution", "admin"], bad: "admin",
        raw: `HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json

{
  "type": "https://tcms.northwind.test/problems/scope-above-role",
  "title": "Scope exceeds owner role",
  "status": 422,
  "detail": "scope 'admin' is not granted to role 'tester'",
  "errors": [{"field": "scopes[2]", "code": "scope_above_role", "value": "admin"}],
  "request_id": "req_01JD7ZK4M2X9"
}`
      }
    }
  }
};
