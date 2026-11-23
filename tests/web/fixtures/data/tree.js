/* Features and cases view data: one product's feature tree with its cases, the selected feature and the filters. Demo data only. */
/* a tree node is a feature (t: "f", with kids and `more` cases not loaded yet) or a case (t: "c") */
/* pos: its place among its feature's cases (or its parent's sub-features); fid: the case's feature */
const kase = (key, title, ver, life, auto, pri, tags, last, pos) => ({ id: "c-" + key, t: "c", key, title, ver, life, auto, pri, tags, last, pos, fid: "f-card" });
const feature = (id, name, kids = [], more = 0, open = false, pos = 0) => ({ id, t: "f", name, kids, more, open, pos });

const cases = () => [
  kase("PAY-101", "Pay with a saved Visa card", 7, "ready", "manual", "high", ["smoke", "visa"], "success", 0),
  kase("PAY-102", "Card is declined with insufficient funds and the order stays unpaid", 3, "ready", "automated", "high", ["decline"], "fail", 1),
  kase("PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out on the first attempt and the customer retries from the order summary page", 2, "draft", "to_automate", "medium", ["3ds", "retry"], "skip", 2),
  kase("PAY-131", "Pay with Maestro (removed)", 4, "deprecated", "manual", "low", [], "ignore", 3),
  kase("PAY-140", "saved_card_token_expired_mid_session", 1, "draft", "manual", "medium", ["token_refresh"], "untested", 4)
];
/* the server's matches for a search or a filter: these case keys */
const only = (...keys) => cases().filter((c) => keys.includes(c.key));
const tree = (card = []) => [
  feature("f-checkout", "Checkout", [feature("f-card", "Card payments", [...card, ...cases()], 9, true, 0), feature("f-wallet", "Apple Pay / Google Pay", [], 9, false, 1), feature("f-3ds", "3-D Secure challenge", [], 8, false, 2)], 0, true, 0),
  feature("f-refunds", "Refunds", [feature("f-partial", "Partial refunds", [], 12, false, 0), feature("f-retry", "refund_webhook_retry", [], 9, false, 1)], 0, true, 1),
  feature("f-subs", "Subscriptions", [feature("f-prorate", "Proration on plan change", [], 12)], 0, true, 2),
  feature("f-payouts", "Payouts", [], 0, false, 3)
];
/* the tree after 3-D Secure challenge was dropped into Card payments */
const dropped = () => {
  const t = tree([feature("f-3ds", "3-D Secure challenge", [], 8)]);
  t[0].kids = t[0].kids.filter((f, i) => i === 0 || f.id !== "f-3ds");
  return t;
};

const desc = `<p>Customers pay at checkout with a <b>saved or new card</b> (Visa, Mastercard, Amex). Covers:</p><ul><li>Authorisation and capture through the PSP</li><li>Declines, with the order left <em>unpaid</em></li><li>Expired saved-card tokens refreshed mid-session</li></ul>`;
const descAgent = desc.replace("</ul>", `<li><mark>3-D Secure step-up when the issuer asks for it (see 3-D Secure challenge)</mark></li></ul>`);

export default {
  base: {
    product: { key: "PAY", name: "Payments" },
    /* the product picked in the tree card's product switcher */
    picked: "PAY",
    readOnly: false,
    products: [
      { key: "PAY", name: "Payments", short: "PAY · Payments", markCls: "", cases: 64, features: 10 },
      { key: "MOB", name: "Mobile app (iOS & Android)", short: "MOB · Mobile app", markCls: "b", cases: 212, features: 9 },
      { key: "ADM", name: "Admin console", short: "ADM · Admin console", markCls: "c", cases: 38, features: 3 },
      { key: "KYC", name: "Partner onboarding and KYC verification service", short: "KYC · Partner onboarding", markCls: "", cases: 0, features: 0 }
    ],
    archived: [{ key: "LEG", name: "Legacy checkout", archivedOn: "Oct 2" }],
    tags: [
      { tag: "smoke", cases: 23 }, { tag: "visa", cases: 6 }, { tag: "decline", cases: 4 }, { tag: "3ds", cases: 5 },
      { tag: "retry", cases: 7 }, { tag: "token_refresh", cases: 2 }, { tag: "regression", cases: 31 }, { tag: "mobile_web", cases: 9 }
    ],
    /* the product has no features */
    empty: false,
    tree: tree(),
    sel: "f-card",
    q: "",
    /* active filters; null shows every case */
    filter: null,
    sort: "manual",
    /* the selected feature's cases as the server sent them (filtered, searched, sorted), and how many match */
    cases: cases(),
    casesTotal: 5,
    feature: {
      id: "f-card", name: "Card payments", parent: "Checkout", owner: "Priya Raman-Castellanos",
      desc,
      edited: { by: "priya", when: "Nov 12, 4:10 PM PT" },
      stats: { cases: 14, ready: 3, draft: 2, automatedPct: 7, automated: 1, toAutomate: 1, ran: 4, ranIn: "2.14.0" },
      latest: { success: 1, fail: 1, skip: 1, ignore: 1, untested: 1 },
      versions: [
        { id: "r-2140", ver: "2.14.0", status: "in_progress" },
        { id: "r-2150", ver: "2.15.0", status: "planned" }
      ],
      plans: [
        { id: "p-reg", name: "Checkout regression", scope: "whole feature" },
        { id: "p-smoke", name: "Release smoke", scope: "PAY-101 only" }
      ],
      cycles: [
        { id: "cy-staging", name: "2.14.0 · staging", status: "open", pinned: 5 },
        { id: "cy-prod", name: "2.13.0 · prod", status: "closed", pinned: 0 }
      ]
    }
  },
  states: {
    filters: {
      filter: { tag: ["visa", "3ds"], status: ["draft", "ready"], result: [], automation: ["manual", "to_automate"], priority: [] },
      cases: only("PAY-101", "PAY-118"), casesTotal: 2
    },
    "new-feature": { sel: "f-checkout", newUnder: "f-checkout", newName: "Saved cards wallet" },
    move: {
      move: {
        src: "f-partial", dest: "f-wallet", from: "f-refunds", pos: 0,
        dests: [
          { v: "root", label: "Payments (top level)", hint: "Product root", root: true },
          { v: "f-checkout", label: "Checkout", hint: "31 cases" },
          { v: "f-card", label: "Checkout / Card payments", hint: "14 cases" },
          { v: "f-wallet", label: "Checkout / Apple Pay / Google Pay", hint: "9 cases" },
          { v: "f-3ds", label: "Checkout / 3-D Secure challenge", hint: "8 cases" },
          { v: "f-refunds", label: "Refunds", hint: "Current parent" },
          { v: "f-partial", label: "Refunds / Partial refunds", hint: "A feature can't go inside itself", dis: true },
          { v: "f-subs", label: "Subscriptions", hint: "12 cases" },
          { v: "f-payouts", label: "Payouts", hint: "Empty" }
        ]
      }
    },
    "drag-folder-into-folder": { drag: { src: "f-3ds", over: "f-card", zone: "in" } },
    "drag-case-reorder": { drag: { src: "c-PAY-140", over: "c-PAY-102", zone: "before" } },
    "drag-invalid": { drag: { src: "f-checkout", over: "f-card", zone: "in" } },
    dropped: { tree: dropped(), moved: "f-3ds", undo: { kind: "f", from: "f-checkout", pos: 2 } },
    "empty-product": { picked: "KYC", tree: [], empty: true, sel: null, feature: null, cases: [], casesTotal: 0 },
    error: {
      error: `HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json

{"type":"https://test-junkie.dev/problems/db-unavailable","title":"Service Unavailable","status":503,"detail":"connection to server at \\"db\\" (172.18.0.3), port 5432 failed: Connection refused\\n\\tIs the server running on that host and accepting TCP/IP connections?","instance":"/api/v1/products/PAY/features","request_id":"req_01JD3K8W2V"}`
    },
    /* the server's matches only: features named like q with their parents, and the cases it found */
    search: {
      q: "card", hits: 3, feats: 1,
      tree: [feature("f-checkout", "Checkout", [feature("f-card", "Card payments", only("PAY-101", "PAY-118", "PAY-140"), 0, true)], 0, true)],
      cases: only("PAY-101", "PAY-118", "PAY-140"), casesTotal: 3
    },
    "search-empty": { q: "invoice", hits: 0, feats: 0, tree: [], cases: [], casesTotal: 0 },
    "desc-saved": { feature: { edited: { when: "just now" } } },
    "desc-agent": { feature: { desc: descAgent, agentEdit: { agent: "triage-bot", when: "Nov 12, 3:14 PM" } } },
    "read-only": { readOnly: true }
  }
};
