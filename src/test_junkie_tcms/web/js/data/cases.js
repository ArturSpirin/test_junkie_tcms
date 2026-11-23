/* Test cases view data: every case in a product, across features. Demo data only. */
const kase = (key, title, feature, version, status, automation, priority, tags, result, updated) => ({ key, title, feature, version, status, automation, priority, tags, result, updated });

export default {
  base: {
    q: "",
    product: { key: "PAY", name: "Payments" },
    total: 64,
    cases: [
      kase("PAY-101", "Pay with a saved Visa card", "Checkout › Card payments", 7, "ready", "manual", "high", ["smoke", "visa"], "success", "Nov 12"),
      kase("PAY-102", "Card is declined with insufficient funds and the order stays unpaid", "Checkout › Card payments", 3, "ready", "automated", "high", ["decline"], "fail", "Nov 11"),
      kase("PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out on the first attempt and the customer retries from the order summary page", "Checkout › Card payments", 2, "draft", "to_automate", "medium", ["3ds", "retry"], "skip", "Nov 13"),
      kase("PAY-131", "Pay with Maestro (removed)", "Checkout › Card payments", 4, "deprecated", "manual", "low", [], "ignore", "Sep 30"),
      kase("PAY-140", "saved_card_token_expired_mid_session", "Checkout › Card payments", 1, "draft", "manual", "medium", ["token_refresh"], "untested", "Nov 14"),
      kase("PAY-152", "Pay with Apple Pay on Safari", "Checkout › Apple Pay / Google Pay", 5, "ready", "automated", "high", ["smoke", "wallet"], "success", "Nov 10"),
      kase("PAY-163", "Google Pay sheet is dismissed and the cart is kept", "Checkout › Apple Pay / Google Pay", 2, "ready", "automated", "medium", ["wallet"], "error", "Nov 9"),
      kase("PAY-177", "3-D Secure challenge passes on the first try", "Checkout › 3-D Secure challenge", 4, "ready", "manual", "critical", ["3ds"], "success", "Nov 8"),
      kase("PAY-204", "Partial refund of one line item", "Refunds › Partial refunds", 6, "ready", "automated", "high", ["refund"], "success", "Nov 7"),
      kase("PAY-210", "Refund to an expired card", "Refunds › Partial refunds", 3, "ready", "manual", "medium", ["refund"], "cancel", "Nov 6"),
      kase("PAY-233", "refund_webhook_retry after a 502 from the PSP", "Refunds › refund_webhook_retry", 2, "draft", "to_automate", "medium", ["webhook", "retry"], "untested", "Nov 5"),
      kase("PAY-301", "Proration when a monthly plan moves to yearly", "Subscriptions › Proration on plan change", 8, "ready", "automated", "high", ["billing"], "success", "Nov 4")
    ],
    /* the feature filter's choices: id, path, short label, case count; unfiled = cases with no feature yet */
    features: [
      { id: "checkout", path: "Checkout", cases: 26 },
      { id: "card", path: "Checkout › Card payments", short: "Card payments", cases: 9 },
      { id: "wallet", path: "Checkout › Apple Pay / Google Pay", short: "Wallets", cases: 9 },
      { id: "refunds", path: "Refunds", cases: 21 },
      { id: "subs", path: "Subscriptions", cases: 12 }
    ],
    unfiled: 5,
    /* active filters (feature ids, case statuses, last results) and the open filter menu */
    filter: { feature: [], status: [], result: [] },
    open: null,
    sort: "updated"
  },
  states: {
    filtered: { filter: { feature: ["card"], status: ["draft", "ready"], result: ["fail", "skip"] } },
    "filter-open": { open: "feature" },
    search: { q: "refund" },
    "search-empty": { q: "invoice" },
    empty: { product: { key: "KYC", name: "Partner onboarding" }, total: 0, cases: [] }
  }
};
