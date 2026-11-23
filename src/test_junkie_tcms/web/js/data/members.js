/* Members view data. Demo data only. */
const member = (handle, userId, email, role, active, agents) => ({ handle, userId, email, role, active, agents });
const invite = (email, role, invitedBy, when, expiresIn) => ({ email, role, invitedBy, when, expiresIn });

const DANA = member("dana", "u_dana", "dana@northwind.test", "owner", "now", 2);
const PRIYA = member("priya", "u_priya", "priya.raman-castellanos@northwind.test", "admin", "12 min ago", 1);
const LEE = member("lee", "u_lee", "lee@northwind.test", "editor", "1 h ago", 0);
const REST = [member("Sam Ito", "u_sam", "sam@northwind.test", "tester", "yesterday", 0), member("Jo Underwood-Bartholomew", "u_jo", "jo.underwood-bartholomew@contractor.example", "viewer", "6 days ago", 0)];

export default {
  base: {
    q: "",
    /* the org's slug in API paths */
    orgSlug: "northwind",
    roles: [
      { role: "owner", desc: "Everything, including the org itself and its owners", scopes: "all scopes" },
      { role: "admin", desc: "Everything except removing owners; manages members, catalog and tokens", scopes: "all scopes · write:catalog" },
      { role: "editor", desc: "Writes cases and plans; can't change products, features or members", scopes: "read · write:execution · write:cases · write:planning" },
      { role: "tester", desc: "Runs cycles and records results", scopes: "read · write:execution" },
      { role: "viewer", desc: "Reads everything in the org, changes nothing", scopes: "read" }
    ],
    members: [DANA, PRIYA, LEE, ...REST],
    /* expiresIn: days left; 0 = expired */
    pending: [invite("mira@northwind.test", "tester", "dana", "2 days ago", 5), invite("ops-lead@northwind.test", "viewer", "priya", "8 days ago", 0)],
    draft: { emails: ["mira.k@northwind.test", "alex.chen@northwind.test"], role: "tester", error: "" },
    /* member being acted on: selected row, open role menu (with its highlighted option), new role, removal */
    sel: null,
    open: null,
    openHl: null,
    roleChange: null,
    remove: null,
    removed: null,
    sent: null
  },
  states: {
    search: { q: "northwind" },
    "search-empty": { q: "mira" },
    "invite-error": { draft: { emails: ["dana@northwind.test"], error: 'problem+json 409: {"title":"Already a member","detail":"dana@northwind.test is already a member of this org"}' } },
    "invite-sent": { sent: { count: 2, invite: invite("mira.k@northwind.test", "tester", "dana", "just now", 7) } },
    "change-role": { sel: "lee", open: "lee", openHl: "tester" },
    "role-changed": { sel: "lee", roleChange: { handle: "lee", role: "tester" } },
    "remove-confirm": { sel: "lee", remove: { handle: "lee", openCycles: 2 } },
    removed: { removed: "lee", members: [DANA, PRIYA, ...REST] }
  }
};
