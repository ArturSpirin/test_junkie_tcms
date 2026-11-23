/* Members view data, in data/members.js's shape. Demo data only. */
const member = (handle, userId, email, role, active, agents) => ({ handle, userId, email, role, active, agents });
const invite = (id, email, role, invitedBy, when, expiresIn) => ({ id, email, role, invitedBy, when, expiresIn });

const DANA = member("dana", "u_dana", "dana@northwind.test", "owner", "now", 2);
const PRIYA = member("priya", "u_priya", "priya.raman-castellanos@northwind.test", "admin", "12 min ago", 1);
const LEE = member("lee", "u_lee", "lee@northwind.test", "editor", "1 h ago", 0);
const SAM = member("Sam Ito", "u_sam", "sam@northwind.test", "tester", "yesterday", 0);
const JO = member("Jo Underwood-Bartholomew", "u_jo", "jo.underwood-bartholomew@contractor.example", "viewer", "6 days ago", 0);
const PENDING = [invite("inv_mira", "mira@northwind.test", "tester", "dana", "2 days ago", 5), invite("inv_ops", "ops-lead@northwind.test", "viewer", "priya", "8 days ago", 0)];

export default {
  base: {
    q: "",
    /* every member (members_list total); members is what the server matched for q */
    total: 5,
    /* the signed-in user's actor id */
    me: "dana",
    roles: [
      { role: "owner", desc: "Everything, including the org itself and its owners", scopes: "all scopes" },
      { role: "admin", desc: "Everything except removing owners; manages members, catalog and tokens", scopes: "all scopes · write:catalog" },
      { role: "editor", desc: "Writes cases and plans; can't change products, features or members", scopes: "read · write:execution · write:cases · write:planning" },
      { role: "tester", desc: "Runs cycles and records results", scopes: "read · write:execution" },
      { role: "viewer", desc: "Reads everything in the org, changes nothing", scopes: "read" }
    ],
    members: [DANA, PRIYA, LEE, SAM, JO],
    /* expiresIn: days left; 0 = expired */
    pending: PENDING,
    pendingTotal: 2,
    draft: { email: "mira.k@northwind.test", role: "tester", error: "" },
    /* member being acted on: selected row, open role menu (with its highlighted option), new role, removal */
    sel: null,
    open: null,
    openHl: null,
    roleChange: null,
    remove: null,
    removed: null,
    /* the invite just created: its link (from InviteCreated.token) is shown once */
    sent: null
  },
  states: {
    search: { q: "northwind", members: [DANA, PRIYA, LEE, SAM] },
    "search-empty": { q: "mira", members: [] },
    "invite-error": { draft: { email: "dana@northwind.test", error: '{"title":"Conflict","status":409,"detail":"Already a member"}' } },
    "invite-sent": {
      pending: [invite("inv_mirak", "mira.k@northwind.test", "tester", "dana", "just now", 7), ...PENDING],
      pendingTotal: 3,
      sent: { email: "mira.k@northwind.test", role: "tester", link: "https://tcms.northwind.test/app?view=accept&token=tji_Hq3vN8kTzP0wLr8sJd2fNc6eHa1uGi5oX4b7h2noYm" }
    },
    "change-role": { sel: "lee", open: "lee", openHl: "tester" },
    "role-changed": { sel: "lee", roleChange: { handle: "lee", role: "tester" } },
    "remove-confirm": { sel: "lee", remove: { handle: "lee" } },
    removed: { removed: "lee", members: [DANA, PRIYA, SAM, JO], total: 4 }
  }
};
