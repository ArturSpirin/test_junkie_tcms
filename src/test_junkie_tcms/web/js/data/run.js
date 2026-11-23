/* Run view data: one cycle's queue, the current case with its steps, and the result being recorded. Demo data only. */
const qcase = (key, title, status) => ({ key, title, status });
/* a dropdown option; icon names an icon in ui.js */
const opt = (v, label, hint, icon) => ({ v, label, hint, icon });

export default {
  base: {
    cycle: { id: "CY-41", queue: "Checkout · Card payments", version: "2.14.0", environment: "staging" },
    /* the cases in this run's queue, with their result so far */
    queue: [
      qcase("PAY-101", "Pay with a saved Visa card", "success"),
      qcase("PAY-102", "Card is declined with insufficient funds and the order stays unpaid", "fail"),
      qcase("PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", "untested"),
      qcase("PAY-140", "saved_card_token_expired_mid_session", "skip"),
      qcase("PAY-144", "Pay with a co-branded Visa debit card", "untested"),
      qcase("PAY-146", "Remove a saved card from the wallet", "untested")
    ],
    /* results recorded in this session that the queue shows before the server recounts: queue index → status */
    queueOver: {},
    /* the open case: queue index, pinned case_version, newest version (0 = pinned is newest), attempt */
    current: { q: 2, step: 1, res: ["success"] },
    case: {
      key: "PAY-118", title: "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", pin: 2, newer: 3, attempt: 1,
      preconditions: "Stripe test mode; 3-D Secure test cards enabled", preShort: "Stripe test mode…", elapsed: "04:12", build: "rc3",
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
      defectUrl: "https://jira.northwind.test/browse/PAY-JIRA-2291", defectKey: "PAY-JIRA-2291"
    },
    skip: { reason: "defect", blockingDefect: "LAB-412" },
    skipReasons: [
      { group: "Blocked" },
      opt("defect", "Blocked by a defect", "Link the defect key below", "ban"),
      opt("env", "Environment down", "staging, sandbox issuer or a dependency", "server"),
      opt("data", "Test data missing", "card, account or fixture not available", "doc"),
      opt("dep", "Depends on a failed step", "an earlier step failed", "link"),
      { group: "Not applicable" },
      opt("na-env", "Not applicable on this environment", "", "eyeoff"),
      opt("flag", "Feature flag off", "3ds_retry_v2 is off on staging", "flag"),
      "-",
      opt("other", "Other…", "Write the reason in the comment", "more")
    ],
    builds: [
      { group: "2.14.0" },
      opt("rc3", "2.14.0-rc3", "Fri Nov 13 · fixes PAY-JIRA-2291", "build"),
      opt("rc2", "2.14.0-rc2", "Thu Nov 12", "build"),
      opt("rc1", "2.14.0-rc1", "Tue Nov 10", "build"),
      { group: "Branches" },
      opt("main", "main@4f2a91c", "deployed to staging 2 h ago", "code"),
      opt("pr", "pr-1182@9be03d1", "preview env", "code"),
      "-",
      opt("none", "Not recorded", "", "dotted")
    ]
  },
  states: {
    "step-failed": { current: { res: ["success", "fail"] } },
    "skip-reason": { current: { res: ["success", "skip"] } },
    drop: { current: { res: ["success", "fail"] } },
    submitted: {
      current: { q: 4, step: 0, res: [] },
      queueOver: { 2: "fail" },
      case: { key: "PAY-144", title: "Pay with a co-branded Visa debit card", pin: 1, newer: 0 },
      saved: { key: "PAY-118", status: "fail", attempt: 1, defects: 1, files: 2, via: "ui" }
    },
    retest: {
      current: { step: 0, res: [] },
      case: { attempt: 2 },
      previous: { status: "fail", by: "lee", at: "Thu Nov 12, 4:20 PM PT", note: "Page shows a spinner forever", defectKey: "PAY-JIRA-2291", fixedIn: "2.14.0-rc3" }
    },
    "upload-error": {
      current: { res: ["success", "fail"] },
      uploadError: {
        file: "screen-recording.mp4",
        raw: "HTTP/1.1 413 Content Too Large\nContent-Type: application/problem+json\n\n{\"type\":\"https://test-junkie.dev/problems/attachment-too-large\",\"title\":\"Content Too Large\",\"status\":413,\"detail\":\"attachment is 148.2 MB; the limit is 50 MB (TJ_TCMS_MAX_ATTACHMENT_MB)\",\"request_id\":\"req_01JD3R7MCV\"}"
      }
    },
    complete: {
      queue: [
        qcase("PAY-101", "Pay with a saved Visa card", "success"),
        qcase("PAY-102", "Card is declined with insufficient funds and the order stays unpaid", "fail"),
        qcase("PAY-118", "Checkout with a card that needs a 3-D Secure challenge after the issuer times out", "fail"),
        qcase("PAY-140", "saved_card_token_expired_mid_session", "skip"),
        qcase("PAY-144", "Pay with a co-branded Visa debit card", "success"),
        qcase("PAY-146", "Remove a saved card from the wallet", "error")
      ]
    }
  }
};
