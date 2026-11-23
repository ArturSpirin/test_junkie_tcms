/* Run view data, in the shape data/run.js gives: one cycle's queue, the current case with its steps, and the
   result being recorded. Demo data only. */
const qcase = (id, key, title, status) => ({ id, key, title, status });
const opt = (v, label, hint, icon) => ({ v, label, hint, icon });

export default {
  base: {
    product: { id: "p_pay", key: "PAY", name: "Payments" },
    cycle: { id: "CY-41", queue: "Checkout · Card payments", version: "2.14.0", environment: "staging", releaseId: "r_214", status: "open" },
    /* the cases in this run's queue, with their result so far */
    queue: [
      qcase("cc_1", "PAY-101", "Pay with a saved Visa card", "success"),
      qcase("cc_2", "PAY-102", "Card is declined with insufficient funds and the order stays unpaid", "fail"),
      qcase("cc_3", "PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", "untested"),
      qcase("cc_4", "PAY-140", "saved_card_token_expired_mid_session", "skip"),
      qcase("cc_5", "PAY-144", "Pay with a co-branded Visa debit card", "untested"),
      qcase("cc_6", "PAY-146", "Remove a saved card from the wallet", "untested")
    ],
    /* results recorded in this session that the queue shows before the server recounts: queue index → status */
    queueOver: {},
    uploadError: null,
    /* the open case: queue index, current step and the step results so far */
    current: { q: 2, step: 1, res: ["success"] },
    /* pinned case_version, newest version (0 = pinned is newest), attempt */
    case: {
      id: "cc_3", key: "PAY-118", title: "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", pin: 2, newer: 3, attempt: 1, build: "2.14.0-rc3",
      preconditions: "Stripe test mode; 3-D Secure test cards enabled", preShort: "Stripe test mode…",
      /* step action and expected result are stored rich text (HTML) */
      steps: [
        { id: "st_a1", action: "Open <b>Checkout</b> with a 3-D Secure test card <code>4000 0027 6000 3184</code>", expected: "The challenge window opens within 3 s" },
        { id: "st_c81p", action: "Wait 30 s without answering the challenge", expected: "Issuer times out; the page shows <i>Verification timed out. Try again.</i>" },
        { id: "st_d4", action: "Press <b>Try again</b> and complete the challenge", expected: "Payment succeeds; order status is <code>paid</code>" },
        { id: "st_e9", action: "Open <b>Orders</b>", expected: "One paid order, no duplicate charge" }
      ]
    },
    /* what a failed step carries: actual result, evidence and the defect */
    failure: {
      actual: "Page shows a spinner forever; no timeout message after 90 s. Console: POST /3ds/poll 504",
      files: [{ name: "3ds-timeout-spinner.png", size: "412 KB" }, { name: "har-checkout.har", size: "1.8 MB" }],
      defectUrl: "https://issues.example.com/browse/PAY-2291", defectKey: "PAY-2291"
    },
    previous: null,
    /* the skip reasons results_create takes, and the skip being recorded */
    skipReasons: [
      { group: "Blocked" },
      opt("defect", "Blocked by a defect", "Link the defect below", "ban"),
      opt("env", "Environment down", "the environment or a dependency is down", "server"),
      opt("data", "Test data missing", "an account or fixture is not available", "doc"),
      opt("dep", "Depends on a failed step", "an earlier step failed", "link"),
      { group: "Not applicable" },
      opt("na_env", "Not applicable on this environment", "", "eyeoff"),
      opt("flag", "Feature flag off", "", "flag"),
      "-",
      opt("other", "Other…", "Write the reason in the comment", "more")
    ],
    skip: { reason: "defect", blockingDefect: "https://issues.example.com/browse/PAY-2291" },
    /* the builds recorded for the product, newest first (cycle_builds) */
    builds: [
      { group: "Recorded builds" },
      opt("2.14.0-rc3", "2.14.0-rc3", "last result Fri Nov 13, 9:10 AM", "build"),
      opt("2.14.0-rc2", "2.14.0-rc2", "last result Thu Nov 12, 4:20 PM", "build"),
      "-",
      opt("", "Not recorded", "", "dotted")
    ]
  },
  states: {
    "step-failed": { current: { res: ["success", "fail"] } },
    "skip-reason": { current: { res: ["success", "skip"] } },
    drop: { current: { res: ["success", "fail"] } },
    submitted: {
      current: { q: 4, step: 0, res: [] },
      queueOver: { 2: "fail" },
      case: { id: "cc_5", key: "PAY-144", title: "Pay with a co-branded Visa debit card", pin: 1, newer: 0 },
      saved: { key: "PAY-118", status: "fail", attempt: 1, defects: 1, files: 2, via: "ui" }
    },
    retest: {
      current: { step: 0, res: [] },
      case: { attempt: 2 },
      previous: { status: "fail", by: "lee", at: "Thu Nov 12, 4:20 PM", note: "Page shows a spinner forever", defectKey: "PAY-2291" }
    },
    "upload-error": {
      current: { res: ["success", "fail"] },
      uploadError: {
        file: "screen-recording.mp4",
        raw: "HTTP/1.1 413 Content Too Large\nContent-Type: application/problem+json\n\n{\"type\":\"https://test-junkie.dev/problems/attachment-too-large\",\"title\":\"Content Too Large\",\"status\":413,\"detail\":\"attachment is 148.2 MB; the limit is 50 MB (TJ_TCMS_MAX_ATTACHMENT_MB)\"}"
      }
    },
    complete: {
      queue: [
        qcase("cc_1", "PAY-101", "Pay with a saved Visa card", "success"),
        qcase("cc_2", "PAY-102", "Card is declined with insufficient funds and the order stays unpaid", "fail"),
        qcase("cc_3", "PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", "fail"),
        qcase("cc_4", "PAY-140", "saved_card_token_expired_mid_session", "skip"),
        qcase("cc_5", "PAY-144", "Pay with a co-branded Visa debit card", "success"),
        qcase("cc_6", "PAY-146", "Remove a saved card from the wallet", "error")
      ]
    }
  }
};
