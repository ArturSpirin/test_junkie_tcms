/* Case editor view data: one case (PAY-101 at v7) and the new-case draft. Demo data only. */
const step = (id, action, expected) => ({ id, action, expected });

export default {
  base: {
    case: {
      key: "PAY-101", title: "Pay with a saved Visa card", version: 7,
      feature: "card", status: "ready", priority: "high", type: "functional", automation: "manual", autoRef: "",
      tags: ["smoke", "visa"],
      links: [{ key: "PAY-JIRA-2210", url: "https://jira.northwind.test/browse/PAY-JIRA-2210" }],
      /* rich text, as the server renders it */
      desc: "<p>A returning customer pays with a card saved on their account. The CVC is not asked again and a receipt is sent.</p>",
      pre: "<ul><li>Customer <code>qa+visa@northwind.test</code> has a saved Visa ending 4242</li><li>Stripe test mode</li></ul>",
      steps: [
        step("st_4kq1", "Open <b>Checkout</b> for an order of <code>$42.00</code>", "The order summary shows <code>$42.00</code> and the saved cards list"),
        step("st_9za7", "Pick the saved card <i>Visa ending 4242</i>", "The card is selected; CVC is not asked again"),
        step("st_2m8x", "Press <b>Pay now</b>", "<p>Payment succeeds:</p><ul><li>order status is <code>paid</code></li><li>a receipt email is queued</li></ul>"),
        step("st_7hd3", "Open <b>Orders</b>", "The order is listed as Paid with the card's last 4 digits")
      ],
      /* the same case exported as Markdown */
      md: `---
key: PAY-101
title: Pay with a saved Visa card
status: ready
priority: high
type: functional
automation: manual
tags: [smoke, visa]
links:
  - url: https://jira.northwind.test/browse/PAY-JIRA-2210
    key: PAY-JIRA-2210
---

## Preconditions

- Customer \`qa+visa@northwind.test\` has a saved Visa ending 4242
- Stripe test mode

## Steps

1. <!-- st_4kq1 --> Open **Checkout** for an order of \`$42.00\`
   - Expected: The order summary shows \`$42.00\` and the saved cards list
2. <!-- st_9za7 --> Pick the saved card *Visa ending 4242*
   - Expected: The card is selected; CVC is not asked again
3. <!-- st_2m8x --> Press **Pay now**
   - Expected: Payment succeeds:
     - order status is \`paid\`
     - a receipt email is queued
4. <!-- st_7hd3 --> Open **Orders**
   - Expected: The order is listed as Paid with the card's last 4 digits`,
      /* where it sits */
      versions: [{ ver: "2.14.0", status: "in_progress", href: "releases.html#detail" }, { ver: "2.13.0", status: "released", href: "releases.html#list" }],
      plans: [{ name: "Checkout regression", via: "feature", href: "plans.html#detail" }, { name: "Release smoke", via: "case", href: "plans.html#list" }],
      cycles: [{ name: "Checkout regression · staging", pin: 7, href: "cycles.html#detail" }, { name: "Release smoke · 2.14.0", pin: 6, href: "cycles.html#list" }],
      /* the current version */
      current: { by: { kind: "agent", name: "triage-bot" }, onBehalf: "dana", via: "mcp", at: "Thu Nov 12, 3:14 PM PT", openCycles: 2, pins: [6, 7] },
      changeNote: "Moved the Orders check after payment; clarified expected"
    },
    /* features of the product a case can sit in */
    folders: [
      { v: "checkout", label: "Checkout", cases: 31 }, { v: "card", label: "Checkout / Card payments", cases: 14 },
      { v: "wallet", label: "Checkout / Apple Pay / Google Pay", cases: 9 }, { v: "3ds", label: "Checkout / 3-D Secure challenge", cases: 8 },
      { v: "refunds", label: "Refunds", cases: 21 }, { v: "partial", label: "Refunds / Partial refunds", cases: 12 },
      { v: "retry", label: "Refunds / refund_webhook_retry", cases: 9 }, { v: "prorate", label: "Subscriptions / Proration on plan change", cases: 12 },
      { v: "payouts", label: "Payouts", cases: 0 }
    ],
    /* tags already used in the product, with their case counts */
    tags: [{ v: "smoke", cases: 23 }, { v: "visa", cases: 6 }, { v: "decline", cases: 4 }, { v: "3ds", cases: 5 }, { v: "retry", cases: 7 }, { v: "token_refresh", cases: 2 }, { v: "regression", cases: 31 }, { v: "mobile_web", cases: 9 }],
    /* reorder: the step order mid-drag; lift is the step being dragged, over the one it is dragged over */
    order: [],
    lift: null, over: null,
    /* the step the server refused, by index */
    invalidStep: null,
    error: ""
  },
  states: {
    reorder: { order: ["st_4kq1", "st_2m8x", "st_9za7", "st_7hd3"], lift: 1, over: 2 },
    "conflict-409": {
      currentVersion: 8,
      error: `HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{"type":"https://test-junkie.dev/problems/stale-version","title":"Conflict","status":409,"detail":"If-Match \\"v7\\" does not match current version \\"v8\\" of case PAY-101","current_version":8,"request_id":"req_01JD3MZ4QF"}`
    },
    "invalid-422": {
      invalidStep: 2,
      error: `HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{"type":"https://test-junkie.dev/problems/validation","title":"Unprocessable Content","status":422,"errors":[{"pointer":"/steps/2/expected/content/1","detail":"unknown node type 'html_block'; raw HTML is not allowed"}],"request_id":"req_01JD3N0B7K"}`
    },
    "new-case": {
      case: {
        key: "PAY-141", title: "", version: 0, status: "draft", automation: "to_automate", tags: [], links: [], desc: "", pre: "",
        steps: [step("st_new1", "", "")], changeNote: "",
        /* plans that pick up a new case in this feature */
        pickedUpBy: [{ name: "Checkout regression", ver: "2.14.0" }]
      }
    }
  }
};
