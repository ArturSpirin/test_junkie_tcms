/* Case editor view data: one case (PAY-101 at v7) and the new-case draft. Demo data only. */
const step = (id, action, expected) => ({ id, action, expected });

export default {
  base: {
    case: {
      id: "cs_101", key: "PAY-101", title: "Pay with a saved Visa card", version: 7,
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
      /* the stored Markdown of each rich field: what a save sends back for a field left alone */
      src: {
        desc: "A returning customer pays with a card saved on their account. The CVC is not asked again and a receipt is sent.",
        pre: "- Customer `qa+visa@northwind.test` has a saved Visa ending 4242\n- Stripe test mode",
        steps: {
          st_4kq1: { action: "Open **Checkout** for an order of `$42.00`", expected: "The order summary shows `$42.00` and the saved cards list" },
          st_9za7: { action: "Pick the saved card *Visa ending 4242*", expected: "The card is selected; CVC is not asked again" },
          st_2m8x: { action: "Press **Pay now**", expected: "Payment succeeds:\n\n- order status is `paid`\n- a receipt email is queued" },
          st_7hd3: { action: "Open **Orders**", expected: "The order is listed as Paid with the card's last 4 digits" }
        }
      },
      /* where it sits: each links to its view by id */
      versions: [{ ver: "2.14.0", status: "in_progress", href: { view: "releases", id: "rel_2140" } }, { ver: "2.13.0", status: "released", href: { view: "releases", id: "rel_2130" } }],
      plans: [{ name: "Checkout regression", via: "feature", href: { view: "plans", id: "pl_checkout" } }, { name: "Release smoke", via: "case", href: { view: "plans", id: "pl_smoke" } }],
      cycles: [{ name: "Checkout regression · staging", pin: 7, href: { view: "cycles", id: "cy_staging" } }, { name: "Release smoke · 2.14.0", pin: 6, href: { view: "cycles", id: "cy_smoke" } }],
      /* the current version */
      current: { by: { kind: "agent", name: "triage-bot" }, onBehalf: "dana", via: "mcp", at: "Thu Nov 12, 3:14 PM PT", openCycles: 2, pins: [6, 7] },
      changeNote: "Moved the Orders check after payment; clarified expected"
    },
    /* features of the product a case can sit in: id, "A / B" label, own name, "A › B" path, cases with sub-features */
    folders: [
      ["checkout", "Checkout", 31], ["card", "Checkout / Card payments", 14], ["wallet", "Checkout / Apple Pay / Google Pay", 9],
      ["3ds", "Checkout / 3-D Secure challenge", 8], ["refunds", "Refunds", 21], ["partial", "Refunds / Partial refunds", 12],
      ["retry", "Refunds / refund_webhook_retry", 9], ["prorate", "Subscriptions / Proration on plan change", 12], ["payouts", "Payouts", 0]
    ].map(([v, label, cases]) => {
      const parts = label.split(" / ");
      // "Apple Pay / Google Pay" is one feature name
      const name = v === "wallet" ? "Apple Pay / Google Pay" : parts[parts.length - 1];
      return { v, label, name, path: v === "wallet" ? "Checkout › Apple Pay / Google Pay" : parts.join(" › "), cases };
    }),
    /* tags already used in the product, with their case counts */
    tags: [{ v: "smoke", cases: 23 }, { v: "visa", cases: 6 }, { v: "decline", cases: 4 }, { v: "3ds", cases: 5 }, { v: "retry", cases: 7 }, { v: "token_refresh", cases: 2 }, { v: "regression", cases: 31 }, { v: "mobile_web", cases: 9 }],
    /* reorder: the step order mid-drag; lift is the step being dragged, over the one it is dragged over */
    order: [],
    lift: null, over: null,
    /* the step the server refused, by index */
    invalidStep: null, invalidField: "expected",
    error: "", currentVersion: null
  },
  states: {
    /* the page loads again after a save: savedAs is the version the save made */
    saved: { savedAs: 8 },
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
        /* the server gives the key on create */
        id: "", key: "", title: "", version: 0, status: "draft", automation: "to_automate", tags: [], links: [], desc: "", pre: "",
        steps: [step("st_new1", "", "")], changeNote: "",
        /* plans that pick up a new case in this feature */
        pickedUpBy: [{ name: "Checkout regression", ver: "2.14.0" }]
      }
    }
  }
};
