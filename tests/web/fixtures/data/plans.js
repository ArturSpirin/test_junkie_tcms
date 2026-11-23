/* Test plans view data, in data/plans.js's shape: the current product's plans, one plan's detail and the new-plan
   and new-cycle forms. Demo data only. */
const plan = (id, name, status, version, scope, cases, results) => ({ id, name, status, version, scope, cases, results });
const entry = (id, kind, label, meta) => ({ id, kind, label, meta });

export default {
  base: {
    q: "",
    total: 4,
    versionFilter: "all",
    statusFilter: ["active", "draft"],
    plans: [
      plan("pl_8k2", "Checkout regression", "active", "2.14.0", "3 features · 1 query", "28 cases", { success: 19, fail: 2, skip: 1, untested: 6 }),
      plan("pl_3m1", "Release smoke", "active", "any version", "18 cases picked", "18 cases", { success: 18 }),
      plan("pl_7w4", "Wallet limits", "draft", "2.15.0", "1 feature", "14 cases", {}),
      plan("pl_2p9", "Payouts v2 sign-off", "archived", "2.13.0", "2 features", "31 cases", { success: 29, fail: 1, skip: 1 })
    ],
    product: { id: "pr_pay", key: "PAY", name: "Payments" },
    detail: {
      id: "pl_8k2", name: "Checkout regression", status: "active", releaseId: "rl_2140", version: "2.14.0", versionStatus: "in_progress",
      entries: [
        entry("pe_1", "feature", "Checkout › Card payments", "all its cases, resolved when the cycle starts · now 5"),
        entry("pe_2", "feature", "Checkout › Wallets", "all its cases, resolved when the cycle starts · now 14"),
        entry("pe_3", "feature", "Checkout › 3-D Secure", "all its cases, resolved when the cycle starts · now 9"),
        entry("pe_4", "query", "tags: visa AND priority: high", "matches 4 · 4 already in an entry above"),
        entry("pe_5", "case", "PAY-210 · Refund to an expired card", "single case · v3 now")
      ],
      /* how the entries resolve when a cycle is made */
      resolve: { features: 3, featureCases: 28, queryNew: 0, cases: 1, pinned: 29, example: { key: "PAY-101", ver: 7 } },
      cycles: [
        { id: "cy_41", name: "Checkout regression · staging", status: "open", pinned: 28 },
        { id: "cy_37", name: "Checkout regression · prod", status: "closed", pinned: 26 }
      ],
      latest: { env: "staging", results: { success: 19, fail: 2, skip: 1, untested: 6 } }
    },
    /* the feature picker of the entry editor */
    features: [
      { id: "ft_1", path: "Checkout › Card payments" },
      { id: "ft_2", path: "Checkout › Wallets" },
      { id: "ft_3", path: "Checkout › 3-D Secure" }
    ],
    draft: {
      name: "Checkout regression", product: "PAY", version: "rl_2140", allFeatures: true, featureCount: 6,
      versions: [{ id: "rl_2150", ver: "2.15.0", status: "planned", features: 0 }, { id: "rl_2140", ver: "2.14.0", status: "in progress", features: 6 }]
    },
    newCycle: {
      environments: ["staging", "prod", "qa-eu"], env: "staging", name: "Checkout regression · staging",
      resolved: [
        { label: "Checkout › Card payments", count: 5, unit: "" },
        { label: "Checkout › Wallets", count: 14, unit: "" },
        { label: "Checkout › 3-D Secure", count: 9, unit: "" },
        { label: "Query: tags: visa AND priority: high", count: 0, unit: "new" },
        { label: "PAY-210", count: 1, unit: "" }
      ],
      deprecated: 2, skipDeprecated: true
    }
  },
  states: {
    search: { q: "checkout", plans: [plan("pl_8k2", "Checkout regression", "active", "2.14.0", "3 features · 1 query", "28 cases", { success: 19, fail: 2, skip: 1, untested: 6 })] },
    "search-empty": { q: "invoice", plans: [] },
    empty: { plans: [], total: 0 }
  }
};
