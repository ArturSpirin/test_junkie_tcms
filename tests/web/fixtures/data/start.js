/* Start view data, in data/start.js's shape: the cycle wizard (scope, mode, machines) and the live cycle it
   starts. Demo data only. */
const result = (key, title, machine, status, time) => ({ key, title, machine, status, time });

export default {
  base: {
    product: { id: "pr_pay", key: "PAY", name: "Payments" },
    version: "2.14.0",
    versionId: "rl_2140",
    releaseId: "rl_2140",
    /* the picks so far, carried in the URL from step to step */
    query: { version: "rl_2140", plan: "pl_8k2", features: null, env: null, name: null, tester: null, order: null, machines: null },
    order: "feature",
    /* the product and version pickers on step 1 */
    products: [{ key: "PAY", name: "Payments", markCls: "" }, { key: "ID", name: "Identity", markCls: "b" }, { key: "WEB", name: "Storefront", markCls: "c" }],
    versions: [{ id: "rl_2150", ver: "2.15.0", hint: "planned" }, { id: "rl_2140", ver: "2.14.0", hint: "in progress · 6 features" }, { id: "rl_2130", ver: "2.13.0", hint: "released" }],
    /* the plan the wizard runs */
    plan: { id: "pl_8k2", name: "Checkout regression", cases: 28, automated: 22, manual: 6 },
    plans: [
      { id: "pl_8k2", name: "Checkout regression", meta: "3 features · 1 query · 28 cases", on: true },
      { id: "pl_3m1", name: "Release smoke", meta: "any version · 18 cases", on: false },
      { id: "pl_7w4", name: "Wallet limits", meta: "draft · scoped to 2.15.0", on: false, cantRun: true },
      { id: "pl_2p9", name: "Payouts v2 sign-off", meta: "archived · 2.13.0", on: false, cantRun: true }
    ],
    features: [
      { id: "ft_1", path: "Checkout › Card payments", cases: 5, on: true },
      { id: "ft_2", path: "Checkout › Wallets", cases: 14, on: true },
      { id: "ft_3", path: "Checkout › 3-D Secure", cases: 9, on: true },
      { id: "ft_4", path: "Payouts › Schedules", cases: 11, on: false },
      { id: "ft_5", path: "Payouts › Reversals", cases: 8, on: false },
      { id: "ft_6", path: "Refunds", cases: 17, on: false }
    ],
    environments: ["staging", "prod", "qa-eu"],
    environment: "staging",
    cycleName: "Checkout regression · staging",
    testers: [{ handle: "lee", name: "Lee Park", role: "tester" }, { handle: "priya", name: "Priya Shah", role: "editor" }, { handle: "dana", name: "Dana Cole", role: "admin" }],
    tester: "lee",
    /* who can take the manual half of a "Both" run */
    mixedTesters: ["lee", "priya"],
    machines: [
      { id: "cn_eu1", name: "CI runner EU 1", status: "online", meta: "Linux · tj 0.8.9 · idle", on: true, can: true },
      { id: "cn_mac", name: "QA lab Mac mini", status: "busy", meta: "macOS 15 · tj 0.8.9 · queues after its current job (about 6 min)", on: true, can: true },
      { id: "cn_perf", name: "Perf box 2", status: "online", meta: "Not allowed for PAY: paired for WEB only", allowed: false },
      { id: "cn_dana", name: "Dana's laptop", status: "offline", meta: "Last heartbeat 3 h ago" }
    ],
    heartbeatWindow: "2 minutes",
    /* the live cycle */
    cycle: {
      id: "cy_41", name: "Checkout regression · staging", mode: "auto", finished: false, queued: false,
      counts: { success: 9, fail: 1, error: 1, untested: 17 },
      done: 11, total: 22, passed: 9, passedPct: 82, failed: 2, failedKeys: ["PAY-118", "PAY-120"], elapsed: "5 min 12 s", left: "6 min",
      jobs: [
        { id: "jb_1", consumerId: "cn_eu1", machine: "CI runner EU 1", features: "Card payments, 3-D Secure", done: 9, total: 14 },
        { id: "jb_2", consumerId: "cn_mac", machine: "QA lab Mac mini", features: "Wallets", done: 2, total: 8 }
      ],
      results: [
        result("PAY-101", "Pay with a saved Visa card", "CI runner EU 1", "success", "4.2 s"),
        result("PAY-102", "Decline on insufficient funds", "CI runner EU 1", "success", "3.1 s"),
        result("PAY-118", "Apple Pay sheet opens on Safari", "QA lab Mac mini", "fail", "12.8 s"),
        result("PAY-120", "Google Pay token refresh", "CI runner EU 1", "error", "0.9 s"),
        result("PAY-131", "3-D Secure challenge, frictionless", "CI runner EU 1", "running", "…"),
        result("PAY-133", "3-D Secure challenge times out", "QA lab Mac mini", "untested", "queued")
      ],
      manual: { count: 6, done: 1, cases: [{ key: "PAY-140", title: "Receipt email layout" }, { key: "PAY-141", title: "Wallet onboarding copy" }] }
    }
  },
  states: {
    "auto-none": {
      machines: [
        { id: "cn_eu1", name: "CI runner EU 1", status: "offline", meta: "Last heartbeat 14 min ago" },
        { id: "cn_mac", name: "QA lab Mac mini", status: "offline", meta: "Last heartbeat 14 min ago" },
        { id: "cn_perf", name: "Perf box 2", status: "offline", meta: "Not allowed for PAY: paired for WEB only", allowed: false },
        { id: "cn_dana", name: "Dana's laptop", status: "offline", meta: "Last heartbeat 3 h ago" }
      ]
    },
    queued: { cycle: { queued: true } },
    "offline-mid": { cycle: { stalled: { machine: "QA lab Mac mini", jobId: "jb_2", since: "2 min", waiting: 6, reassignTo: "CI runner EU 1", reassignId: "cn_eu1" } } },
    "cancel-cases": { cycle: { stalled: { machine: "QA lab Mac mini", jobId: "jb_2", since: "2 min", waiting: 6, reassignTo: "CI runner EU 1", reassignId: "cn_eu1" } } },
    reassigned: { moved: { count: 6, to: "CI runner EU 1" } },
    mixed: { cycle: { mode: "mixed", manualTester: "lee" } },
    done: {
      cycle: {
        finished: true, counts: { success: 19, fail: 2, error: 1, skip: 0, untested: 6 },
        done: 22, passed: 19, passedPct: 86, failed: 3, failedKeys: ["PAY-118", "PAY-120", "PAY-127"], elapsed: "11 min 40 s"
      }
    },
    "done-mixed": {
      cycle: {
        mode: "mixed", manualTester: "lee", finished: true, counts: { success: 19, fail: 2, error: 1, skip: 0, untested: 6 },
        done: 22, passed: 19, passedPct: 86, failed: 3, failedKeys: ["PAY-118", "PAY-120", "PAY-127"], elapsed: "11 min 40 s"
      }
    }
  }
};
