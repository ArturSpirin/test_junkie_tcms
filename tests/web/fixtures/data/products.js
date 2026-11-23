/* Products view data (the mock's fixture, for the render test). Demo data only. */
const product = (key, name, markCls, desc, features, cases, versions, results, latest) => ({ key, name, markCls, desc, features, cases, versions, results, latest });

export default {
  base: {
    q: "",
    /* every product; products holds the ones the server matched for q */
    total: 3,
    products: [
      product("PAY", "Payments", "", "Card, wallet and bank payments; refunds", 9, 412, 3, { success: 248, fail: 14, error: 3, skip: 9, untested: 22 }, "2.14.0 in progress"),
      product("ID", "Identity", "b", "Sign-up, sign-in, MFA and account recovery", 6, 188, 2, { success: 120, fail: 4, skip: 2, untested: 10 }, "3.2.0 planned"),
      product("WEB", "Storefront", "c", "Catalog, cart and the checkout front end", 11, 530, 4, { success: 301, fail: 22, error: 6, ignore: 4, skip: 11, untested: 40 }, "5.0.0 in progress")
    ],
    detail: {
      key: "PAY", name: "Payments", desc: "Card, wallet and bank payments; refunds", owner: "dana",
      kpis: { versions: 3, inProgress: 1, planned: 1, features: 9, topLevel: 3, cases: 412, automatedPct: 31, plans: 4, plansActive: 2 },
      versions: [
        { id: "rel_215", ver: "2.15.0", status: "planned", when: "Due Dec 18", features: 4, cycles: 0, results: {} },
        { id: "rel_214", ver: "2.14.0", status: "in_progress", when: "Due Nov 27", features: 6, cycles: 3, results: { success: 62, fail: 4, error: 1, skip: 3, untested: 18 } },
        { id: "rel_213", ver: "2.13.0", status: "released", when: "Released Oct 30", features: 5, cycles: 4, results: { success: 140, fail: 2, skip: 4 } }
      ],
      features: [
        { path: "Checkout › Card payments", cases: 5, changedIn: "2.14.0" },
        { path: "Checkout › Wallets", cases: 14, changedIn: "2.14.0" },
        { path: "Refunds › Partial refunds", cases: 22, changedIn: "2.15.0" },
        { path: "Payouts", cases: 31, changedIn: "2.13.0" }
      ],
      plans: [
        { id: "pl_checkout", name: "Checkout regression", meta: "2.14.0 · 3 features · 46 cases", cycles: 2 },
        { id: "pl_smoke", name: "Release smoke", meta: "Any version · 18 cases", cycles: 5 }
      ]
    },
    draft: { key: "KYC", name: "KYC · Partner onboarding", desc: "Identity checks for partner merchants" },
    /* products whose feature tree a new product can copy */
    copyFrom: [{ key: "PAY", name: "Payments", markCls: "", features: 9 }, { key: "ID", name: "Identity", markCls: "b", features: 6 }]
  },
  states: {
    search: { q: "pay", products: [product("PAY", "Payments", "", "Card, wallet and bank payments; refunds", 9, 412, 3, { success: 248, fail: 14, error: 3, skip: 9, untested: 22 }, "2.14.0 in progress")] },
    "search-empty": { q: "billing", products: [] },
    created: { created: product("KYC", "Partner onboarding", "", "Identity checks for partner merchants", 0, 0, 1, {}, "1.0.0 planned") },
    empty: { products: [], total: 0 },
    "new-first": { products: [], total: 0, draft: { key: "PAY", name: "Payments", desc: "" } }
  }
};
