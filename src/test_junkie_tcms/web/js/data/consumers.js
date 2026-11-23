/* Consumers view data: paired machines, the pairing flow and one machine's detail. Demo data only.
   A machine is named by the person who pairs it; TCMS never shows its hostname, user or paths. */
const machine = (name, status, heartbeat, os, tj, python, products, projects, jobsToday) => ({ name, status, heartbeat, os, tj, python, products, projects, jobsToday });
const job = (name, state, project, detail, done, total) => ({ name, state, project, detail, done, total });

export default {
  base: {
    q: "",
    filter: "all",
    machines: [
      machine("CI runner EU 1", "online", "4 s ago", "Linux", "0.8.9", "3.12", ["PAY", "ID"], 3, 52),
      machine("QA lab Mac mini", "busy", "2 s ago", "macOS 15", "0.8.9", "3.11", ["PAY"], 2, 37),
      machine("Perf box 2", "online", "11 s ago", "Linux", "0.8.8", "3.12", ["WEB"], 1, 8),
      machine("Dana's laptop", "offline", "3 h ago", "Windows 11", "0.8.7", "3.10", ["PAY", "WEB"], 1, 0)
    ],
    /* pairing: RFC 8628 device flow; the person approving names the machine */
    pair: {
      server: "https://tcms.northwind.test",
      codeLength: 8, ttlMin: 10, typed: "KQ4M7XR", expiresIn: "8 min 42 s",
      name: "QA lab Mac mini", sentName: "QA lab Mac mini",
      os: "macOS 15", tj: "0.8.9", python: "3.11", projects: ["payments-suite", "payments-smoke"],
      products: ["PAY"], acceptNow: true
    },
    paired: { name: "QA lab Mac mini", products: ["PAY"] },
    machine: {
      id: "c_7f2", name: "QA lab Mac mini", status: "busy", heartbeat: "2 s ago", silentFor: "3 h 12 min", lastHeartbeat: "11:02 AM PT",
      jobsToday: 37, rejectedToday: 1, testsFound: 412, testsLinked: 384, tj: "0.8.9", python: "3.11", os: "macOS 15",
      products: ["PAY"],
      projects: [{ name: "payments-suite", products: ["PAY"] }, { name: "payments-smoke", products: ["PAY"] }],
      jobs: [
        job("Checkout regression · staging", "running", "payments-suite", "Card payments, Wallets", 14, 28),
        job("Release smoke · 2.14.0", "queued", "payments-smoke", "tags: smoke · timeout 10 min")
      ],
      /* heartbeats per hour (long-poll wait=30 → about 120 an hour), last 24 hours from startHour, with jobs run */
      hb: {
        expected: 120, startHour: 7, tz: "PT",
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
      ]
    },
    renameTo: "QA lab Mac mini (2nd floor)"
  },
  states: {
    "filter-online": { filter: "online" },
    "filter-busy": { filter: "busy" },
    "filter-offline": { filter: "offline" },
    search: { q: "mac" },
    "search-empty": { q: "jenkins" },
    "pair-noname": { pair: { name: "" } },
    "detail-hover": { hoverCol: 7 },
    "job-rejected": {
      machine: {
        jobs: [
          job("Checkout regression · staging", "running", "payments-suite", "Card payments, Wallets", 14, 28),
          job("Release smoke · 2.14.0", "queued", "payments-smoke", "tags: smoke · timeout 10 min"),
          job("Wallet limits · qa-eu", "rejected", "wallet-suite")
        ],
        rejectError: "409 project_not_registered: wallet-suite"
      }
    },
    offline: { machine: { status: "offline" } },
    empty: { machines: [] }
  }
};
