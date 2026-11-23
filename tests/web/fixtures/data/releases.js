/* Versions (releases) view data (the mock's fixture, for the render test). Demo data only. */
const version = (ver, status, when, features, plans, cycles, results, summary) => ({ id: "rel_" + ver, ver, status, when, features, plans, cycles, results, summary });
const feature = (path, cases, inVersion, sub = false) => ({ id: "ft_" + path.length, path, cases, inVersion, sub });

export default {
  base: {
    product: { key: "PAY", name: "Payments" },
    versions: [
      version("2.15.0", "planned", "Target Dec 18", 4, 1, 0, {}, "Wallet limits, partial refunds"),
      version("2.14.0", "in_progress", "Target Nov 27", 6, 2, 3, { success: 62, fail: 4, error: 1, skip: 3, untested: 18 }, "3-D Secure 2, saved cards"),
      version("2.13.0", "released", "Released Fri Oct 30", 5, 1, 4, { success: 140, fail: 2, skip: 4 }, "Payouts v2"),
      version("2.12.1", "cancelled", "Cancelled Oct 9", 1, null, 0, {}, "Hotfix folded into 2.13.0")
    ],
    detail: {
      id: "rel_2.14.0", ver: "2.14.0", status: "in_progress", target: "Thu Nov 27", features: 6, plans: 2, cycles: 3,
      kpis: { inScope: 46, fromFeatures: 6, executedPct: 79, executed: 70, cycleCases: 88, passPct: 89 },
      /* the product's features; inVersion marks the ones this version changes */
      tree: [
        feature("Checkout › Card payments", 5, true, true),
        feature("Checkout › Wallets", 14, true, true),
        feature("Checkout › 3-D Secure", 9, true, true),
        feature("Refunds", 22, true),
        feature("Refunds › Partial refunds", 8, false, true),
        feature("Payouts", 31, true),
        feature("Disputes", 17, false)
      ],
      testPlans: [
        { id: "pl_checkout", name: "Checkout regression", status: "active", scope: "3 features" },
        { id: "pl_smoke", name: "Release smoke", status: "active", scope: "18 cases" }
      ],
      cycleList: [
        { id: "cy_card", name: "Checkout · Card payments · staging", status: "open" },
        { id: "cy_regression", name: "Checkout regression · staging", status: "open" },
        { id: "cy_smoke", name: "Release smoke · prod", status: "closed" }
      ],
      /* what is still open when the version is marked released */
      untested: 18, openCycles: 2
    },
    draft: {
      ver: "2.16.0", status: "planned", name: "Spring wallets", target: "jan22", copyFrom: "2.15.0", notes: "",
      targets: [
        { v: "dec18", label: "Fri Dec 18", hint: "after 2.15.0" },
        { v: "jan22", label: "Fri Jan 22", hint: "5 weeks after 2.15.0" },
        { v: "feb19", label: "Fri Feb 19", hint: "" }
      ],
      /* versions whose feature list a new version can copy */
      copyable: ["2.15.0", "2.14.0"]
    },
    noVersionsFor: "KYC"
  },
  states: {
    empty: { versions: [] }
  }
};
