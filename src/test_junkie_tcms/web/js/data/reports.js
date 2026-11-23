/* Reports view data. Demo data only. */
const product = (key, name, cases, automatedPct, results, openCycles) => ({ key, name, cases, automatedPct, results, openCycles });
const day = (date, success, fail, error, skip) => ({ date, success, fail, error, skip });
const release = (ver, name, status, due, hint) => ({ ver, name, status, due, hint });
const feature = (path, cases, results, drift, driftNote, readiness) => ({ path, cases, results, drift, driftNote, readiness });
/* by is { kind, id } (a person's handle or an agent's name), or null when nobody ran it; noteKind: "attempt", "issue" or "" */
const kase = (key, title, ranOn, current, result, by, when, note, noteKind, why) => ({ key, title, ranOn, current, result, by, when, note, noteKind, why });
const run = (ver, env, when, results) => ({ ver, env, when, results });

export default {
  base: {
    period: { value: "30d" },
    /* the product the product and feature reports are about */
    product: { key: "PAY", name: "Payments", cases: 142 },
    org: {
      kpis: { readyCases: 553, products: 4, successPct: 93, automatedPct: 39, openCycles: 8, untested: 161 },
      trend: {
        totals: { success: 581, fail: 38, error: 11, skip: 15 },
        results: 645, peakDay: "Thu Nov 12", byAgentsPct: 71,
        days: [
          day("2026-11-01", 30, 3, 1, 1), day("2026-11-02", 42, 4, 0, 2), day("2026-11-03", 18, 1, 0, 0), day("2026-11-04", 8, 0, 0, 0),
          day("2026-11-05", 51, 6, 2, 1), day("2026-11-06", 47, 3, 1, 3), day("2026-11-07", 39, 2, 0, 1), day("2026-11-08", 44, 5, 1, 0),
          day("2026-11-09", 52, 2, 0, 2), day("2026-11-10", 21, 1, 0, 0), day("2026-11-11", 12, 0, 0, 0), day("2026-11-12", 58, 7, 3, 2),
          day("2026-11-13", 61, 4, 1, 1), day("2026-11-14", 49, 3, 2, 2)
        ]
      },
      products: [
        product("PAY", "Payments", 142, 61, { success: 412, fail: 14, error: 4, skip: 9, ignore: 2, cancel: 1, untested: 37 }, 4),
        product("MOB", "Mobile app (iOS & Android)", 310, 22, { success: 520, fail: 33, error: 8, skip: 12, ignore: 3, untested: 120 }, 3),
        product("ADM", "Admin console", 64, 80, { success: 88, fail: 1, untested: 4 }, 1),
        product("KYC", "Partner onboarding and KYC verification service", 37, 0, {}, 0)
      ]
    },
    release: {
      ver: "2.14.0", name: "Spring checkout", due: "Fri Nov 27", cycles: 4, open: false,
      kpis: { cases: 53, ran: 35, ranPct: 66, fail: 2, error: 1, skip: 1, drift: 3 },
      latest: { success: 29, fail: 2, error: 1, ignore: 2, skip: 1, untested: 18 },
      driftExample: { key: "PAY-101", from: 7, to: 8 },
      releases: [
        release("2.14.0", "Spring checkout", "in_progress", "Fri Nov 27", "in_progress · due Fri Nov 27 · 4 release cycles"),
        release("2.15.0", "Wallet upgrade", "planned", "Fri Dec 18", "planned · due Fri Dec 18 · no cycles yet"),
        release("2.16.0", "Payouts v2", "planned", "Fri Jan 22", "planned · due Fri Jan 22"),
        release("2.13.0", "Saved cards", "released", "", "released Fri Oct 30 · 6 cycles"),
        release("2.12.0", "Refund webhooks", "released", "", "released Fri Oct 9 · 5 cycles")
      ],
      features: [
        feature("Checkout › Card payments", 15, { success: 9, fail: 1, error: 1, ignore: 1, skip: 1, untested: 2 }, 1, "PAY-101 v8 is newer than pinned v7", "at risk"),
        feature("Checkout › 3-D Secure challenge", 8, { success: 3, ignore: 1, untested: 4 }, 0, "", "in progress"),
        feature("Refunds › Partial refunds", 12, { success: 11, fail: 1 }, 0, "", "at risk"),
        feature("Subscriptions › Proration on plan change", 12, { untested: 12 }, 0, "", "not started"),
        feature("Refunds › refund_webhook_retry", 6, { success: 6 }, 2, "2 cases edited after their result", "ready")
      ]
    },
    feature: {
      path: "Checkout › Card payments", name: "Card payments",
      kpis: { cases: 15, results: { success: 9, fail: 1, error: 1, ignore: 1, skip: 1, untested: 2 }, successPct: 77, drift: 1 },
      cases: [
        kase("PAY-101", "Pay with a saved Visa card", 7, 8, "fail", { kind: "person", id: "lee" }, "Thu Nov 12, 4:20 PM PT", "attempt 2", "attempt", ""),
        kase("PAY-102", "Card is declined with insufficient_funds and the user sees the retry banner", 3, 3, "success", { kind: "agent", id: "ci-reporter" }, "Fri Nov 13, 2:05 AM PT", "automated", "", ""),
        kase("PAY-118", "Pay with a Mastercard that requires 3-D Secure when the issuer's ACS times out after the challenge is shown to the user on a slow connection", 2, 2, "skip", { kind: "person", id: "priya" }, "Thu Nov 12, 1:10 PM PT", "LAB-412", "issue", "Blocked by LAB-412: sandbox issuer down"),
        kase("PAY-141", "Card vault returns 500 while saving a card", 2, 2, "error", { kind: "agent", id: "ci-reporter" }, "Fri Nov 13, 2:07 AM PT", "automated", "", "TimeoutError in harness"),
        kase("PAY-140", "card_on_file_update_after_expiry", 1, 1, "untested", null, "", "", "", ""),
        kase("PAY-107", "Save a new card during checkout", 4, 4, "success", { kind: "person", id: "lee" }, "Wed Nov 11, 3:44 PM PT", "", "", "")
      ],
      history: [
        run("2.14.0", "staging", "now", { success: 9, fail: 1, error: 1, ignore: 1, skip: 1, untested: 2 }),
        run("2.13.0", "prod", "Oct 30", { success: 13, fail: 1 }),
        run("2.13.0", "staging", "Oct 27", { success: 11, fail: 2, cancel: 1 }),
        run("2.12.0", "prod", "Oct 9", { success: 12, skip: 1 }),
        run("2.12.0", "staging", "Oct 6", { success: 10, fail: 2, error: 1 })
      ]
    }
  },
  states: {
    "period-custom": { period: { value: "custom", open: true } },
    /* the chart column whose tooltip is pinned open */
    "org-hover": { pinDay: 11 },
    "pick-release": { release: { open: true } },
    empty: { product: { key: "KYC", name: "Partner onboarding and KYC verification service", cases: 37 } }
  }
};
