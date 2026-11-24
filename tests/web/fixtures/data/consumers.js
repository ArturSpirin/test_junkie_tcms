/* Consumers view data: paired machines, the pairing flow and one machine's detail. Demo data only, in the shape
   web/js/data/consumers.js gives. A machine is named by the person who pairs it; TCMS never shows its hostname,
   user or paths. */
const machine = (id, name, status, heartbeat, os, tj, python, products, projects, paused = false) => ({ id, name, status, paused, heartbeat, os, tj, python, products, projects });
const job = (id, name, state, project, detail, total, reason = "") => ({ id, cycleId: "cy_" + id, name, state, project, detail, done: null, total, reason });

const MACHINES = [
  machine("c_1a0", "CI runner EU 1", "online", "4 s ago", "Linux", "0.8.9", "3.12", ["PAY", "ID"], 3),
  machine("c_7f2", "QA lab Mac mini", "busy", "2 s ago", "macOS 15", "0.8.9", "3.11", ["PAY"], 2),
  machine("c_3b9", "Perf box 2", "online", "11 s ago", "Linux", "0.8.8", "3.12", ["WEB"], 1, true),
  machine("c_9d4", "Dana's laptop", "offline", "3 h ago", "Windows 11", "0.8.7", "3.10", ["PAY", "WEB"], 1)
];
const only = (status) => MACHINES.filter((m) => m.status === status);

export default {
  base: {
    q: "",
    filter: "all",
    counts: { all: 4, online: 2, busy: 1, offline: 1 },
    /* what the server matched for q and filter */
    machines: MACHINES,
    /* pairing: RFC 8628 device flow; the person approving names the machine */
    pair: {
      code: "KQ4M7XR", server: "https://tcms.northwind.test",
      codeLength: 8, ttlMin: null, typed: "KQ4M7XR", expiresIn: "8 min 42 s",
      name: "QA lab Mac mini",
      os: "macOS 15", tj: "0.8.9", python: "3.11", projects: ["payments-suite", "payments-smoke"],
      products: ["PAY"], acceptNow: true
    },
    paired: { id: "c_7f2", name: "QA lab Mac mini", products: ["PAY"] },
    machine: {
      id: "c_7f2", name: "QA lab Mac mini", status: "busy", paused: false, heartbeat: "2 s ago", silentFor: "3 h 12 min", lastHeartbeat: "11:02 AM",
      jobsToday: 37, rejectedToday: 1, testsFound: 412, testsLinked: 384, tj: "0.8.9", python: "3.11", os: "macOS 15",
      products: ["PAY"],
      projects: [{ name: "payments-suite", products: [] }, { name: "payments-smoke", products: [] }],
      jobs: [
        job("j_1", "Checkout regression", "running", "payments-suite", "staging · 28 tests · timeout 30 min", 28),
        job("j_2", "Release smoke · 2.14.0", "queued", "payments-smoke", "staging · 12 tests · timeout 10 min", 12)
      ],
      rejectError: "",
      /* heartbeats and jobs per hour, the last 24 hours from startHour; expected is null (the API does not say) */
      hb: {
        expected: null, startHour: 7, tz: "PST",
        beats: [118, 120, 119, 120, 117, 120, 120, 96, 0, 0, 64, 120, 120, 119, 120, 118, 120, 120, 112, 120, 120, 119, 120, 61],
        jobs: [2, 1, 0, 3, 1, 0, 2, 4, 0, 0, 1, 2, 5, 3, 1, 0, 2, 1, 3, 2, 1, 0, 2, 1]
      },
      rescanned: "6 min ago",
      tests: [
        { ref: "payments.checkout.test_card::CardPayments::test_visa_3ds_challenge", caseKey: "PAY-101" },
        { ref: "payments.checkout.test_card::CardPayments::test_declined_card", caseKey: "PAY-102" },
        { ref: "payments.checkout.test_wallet::Wallets::test_apple_pay_token", caseKey: "PAY-152" },
        { ref: "payments.refunds.test_refund::Refunds::test_refund_expired_card", caseKey: "PAY-210" },
        { ref: "payments.refunds.test_refund::Refunds::test_partial_refund_rounding", caseKey: null }
      ],
      allTests: false
    },
    renameTo: "QA lab Mac mini",
    hoverCol: 7
  },
  states: {
    "filter-online": { filter: "online", machines: only("online") },
    "filter-busy": { filter: "busy", machines: only("busy") },
    "filter-offline": { filter: "offline", machines: only("offline") },
    search: { q: "mac", machines: MACHINES.filter((m) => m.name.includes("Mac")) },
    "search-empty": { q: "jenkins", machines: [] },
    "pair-noname": { pair: { name: "" } },
    rename: { renameTo: "QA lab Mac mini (2nd floor)" },
    "job-rejected": {
      machine: {
        jobs: [
          job("j_1", "Checkout regression", "running", "payments-suite", "staging · 28 tests · timeout 30 min", 28),
          job("j_2", "Release smoke · 2.14.0", "queued", "payments-smoke", "staging · 12 tests · timeout 10 min", 12),
          job("j_3", "Wallet limits", "rejected", "wallet-suite", "qa-eu · 9 tests · timeout 30 min", 9, "project_not_registered: wallet-suite")
        ],
        rejectError: "project_not_registered: wallet-suite"
      }
    },
    offline: { machine: { status: "offline" } },
    empty: { counts: { all: 0, online: 0, busy: 0, offline: 0 }, machines: [] }
  }
};
