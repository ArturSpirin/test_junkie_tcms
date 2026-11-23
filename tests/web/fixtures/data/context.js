/* Static context: the org, the signed-in user and the current product and version. Demo data only. */
export default {
  app: { version: "1.0.0", hosting: "self-hosted", openapi: "/api/v1/openapi.json" },
  today: "2026-11-14",
  org: { id: "nw", name: "Northwind QA" },
  orgs: [
    { id: "nw", name: "Northwind QA", markCls: "", role: "admin", products: 3 },
    { id: "ac", name: "Acme Platform", markCls: "b", role: "tester", products: 7 },
    { id: "oss", name: "test_junkie OSS", markCls: "c", role: "viewer", products: 1 }
  ],
  user: { handle: "dana", role: "admin" },
  /* handle: [name, initials, avatar class] */
  people: { dana: ["Dana Whitfield", "DW", ""], lee: ["Lee Okafor", "LO", "b"], priya: ["Priya Raman-Castellanos", "PR", "c"] },
  product: { key: "PAY", name: "Payments" },
  version: { ver: "2.14.0", status: "in progress" },
  products: [
    { key: "PAY", name: "Payments", markCls: "", features: 9, cases: 412 },
    { key: "ID", name: "Identity", markCls: "b", features: 6, cases: 188 },
    { key: "WEB", name: "Storefront", markCls: "c", features: 11, cases: 530 }
  ],
  versions: [
    { ver: "2.15.0", status: "planned", when: "due Dec 18" },
    { ver: "2.14.0", status: "in progress", when: "due Nov 27" },
    { ver: "2.13.0", status: "released", when: "Oct 30" }
  ],
  nav: { products: 3, features: 9, plans: 4 },
  mcp: { up: true }
};
