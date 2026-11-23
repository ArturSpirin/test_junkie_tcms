/* Case version history view data, in data/versions.js's shape. Demo data only. */
/* kind: person, agent or token; via: ui, api or mcp; forWho: the person an agent acted for */
const version = (n, kind, who, via, at, note, forWho = "") => ({ n, kind, who, via, at, note, forWho });
const VERSIONS = [
  version(7, "agent", "triage-bot", "mcp", "Thu Nov 12, 3:14 PM PT", "Moved the Orders check after payment; clarified expected", "dana"),
  version(6, "person", "lee", "ui", "Tue Nov 10, 11:02 AM PT", "Added receipt email check"),
  version(5, "person", "dana", "ui", "Mon Nov 2, 4:40 PM PT", "Restored v3 (cases_restore)"),
  version(4, "token", "tjt_8f3k2a1q", "api", "Fri Oct 30, 9:15 AM PT", "Bulk import from CSV"),
  version(3, "person", "priya", "ui", "Wed Oct 21, 2:05 PM PT", ""),
  version(2, "person", "dana", "ui", "Tue Oct 20, 10:30 AM PT", ""),
  version(1, "person", "dana", "ui", "Tue Oct 20, 10:12 AM PT", "Created")
];

export default {
  base: {
    case: { id: "cs_pay101", key: "PAY-101", title: "Pay with a saved Visa card", product: "Payments", productKey: "PAY", feature: "Card payments", featureId: "ft_cards", version: 7 },
    /* the restore dialog's change note */
    draft: { note: "Restored v6" },
    /* the two versions picked to compare: a (From) and b (To) */
    pick: { a: 6, b: 7 },
    versions: VERSIONS,
    /* what changed between the picked versions; rich text is Markdown (`code`), del/ins mark removed and added text */
    diff: {
      moves: [{ step: "st_7hd3", title: "Open Orders", from: 3, to: 4 }, { step: "st_2m8x", title: "Press Pay now", from: 4, to: 3 }],
      fields: [
        { label: "Step st_2m8x · expected", from: [{ text: "Payment succeeds and order status is `paid`" }], to: [{ text: "Payment succeeds" }, { del: " and order status is paid" }, { ins: ": order status is `paid`; a receipt email is queued" }] },
        { label: "Tags", from: [{ text: "smoke" }], to: [{ text: "smoke, " }, { ins: "visa" }] }
      ],
      note: { from: "Added receipt email check", to: "Moved the Orders check after payment; clarified expected" },
      unchanged: "Title, preconditions, steps st_4kq1 and st_9za7, priority, type, links"
    },
    /* cycles the case is in, with the version each one pinned */
    used: [
      { id: "cy_card_staging", cycle: "Checkout · Card payments · staging", release: "2.14.0", pinned: 6, result: "success", note: "has a result: can refresh to v7", open: true },
      { id: "cy_smoke_nightly", cycle: "Smoke · nightly", release: "", pinned: 7, result: "untested", note: "current", open: true },
      { id: "cy_checkout_prod", cycle: "Checkout · 2.13.0 · prod", release: "2.13.0", pinned: 4, result: "success", note: "closed", open: false }
    ]
  },
  states: {
    compare: { pick: { a: 3, b: 7 } },
    "restore-confirm": { pick: { a: 5, b: 7 }, draft: { note: "Restored v5" } },
    restored: { pick: { a: 5, b: 8 }, versions: [version(8, "person", "dana", "ui", "Fri Nov 13, 10:05 AM PT", "Restored v5"), ...VERSIONS] }
  }
};
