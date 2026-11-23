/* Test plans view data: the current product's plans, one plan's detail and the new-plan and new-cycle forms. Demo data only. */
const plan = (name, status, version, scope, cases, results) => ({ name, status, version, scope, cases, results });
const entry = (kind, label, meta) => ({ kind, label, meta });

export default {
  base: {
    q: "",
    versionFilter: "all",
    statusFilter: ["active", "draft"],
    plans: [
      plan("Checkout regression", "active", "2.14.0", "3 features · 1 query", "28 cases", { success: 19, fail: 2, skip: 1, untested: 6 }),
      plan("Release smoke", "active", "any version", "18 cases picked", "18 cases", { success: 18 }),
      plan("Wallet limits", "draft", "2.15.0", "1 feature", "14 cases", {}),
      plan("Payouts v2 sign-off", "archived", "2.13.0", "2 features", "31 cases", { success: 29, fail: 1, skip: 1 })
    ],
    detail: {
      id: "pl_8k2", name: "Checkout regression", status: "active", version: "2.14.0", versionStatus: "in_progress",
      entries: [
        entry("feature", "Checkout › Card payments", "all its cases, resolved when the cycle starts · now 5"),
        entry("feature", "Checkout › Wallets", "all its cases · now 14"),
        entry("feature", "Checkout › 3-D Secure", "all its cases · now 9"),
        entry("query", "tags: visa AND priority: high", "matches 4 · 4 already in a feature above"),
        entry("case", "PAY-210 · Refund to an expired card", "single case · v3 now")
      ],
      /* how the entries resolve when a cycle is made */
      resolve: { features: 3, featureCases: 28, queryNew: 0, cases: 1, pinned: 29, example: { key: "PAY-101", ver: 7 } },
      cycles: [
        { name: "Checkout regression · staging", status: "open", pinned: 28, href: "cycles.html#detail" },
        { name: "Checkout regression · prod", status: "closed", pinned: 26, href: "cycles.html#closed" }
      ],
      latest: { env: "staging", results: { success: 19, fail: 2, skip: 1, untested: 6 } }
    },
    draft: {
      name: "Checkout regression", product: "PAY", version: "2.14.0", allFeatures: true, featureCount: 6,
      versions: [{ ver: "2.15.0", status: "planned" }, { ver: "2.14.0", status: "in progress", features: 6 }]
    },
    newCycle: {
      environments: ["staging", "prod", "qa-eu"], env: "staging", name: "Checkout regression · staging",
      resolved: [
        { label: "Checkout › Card payments", count: 5 },
        { label: "Checkout › Wallets", count: 14 },
        { label: "Checkout › 3-D Secure", count: 9 },
        { label: "Query: tags visa AND priority high", count: 0, unit: "new" },
        { label: "PAY-210", count: 1 }
      ],
      deprecated: 2, skipDeprecated: true
    }
  },
  states: {
    search: { q: "checkout" },
    "search-empty": { q: "invoice" },
    empty: { plans: [] }
  }
};
