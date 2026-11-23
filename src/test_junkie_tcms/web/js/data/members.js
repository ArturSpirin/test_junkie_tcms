/* Members adapter (docs/app-api-contract.md §12): members_list (name or email search is the server's q),
   invites_list, agents_list for "owns N agents", and the writes: invites_create (one email and a role; the
   InviteCreated.token is shown once as the invite link, no email is sent), invites_revoke, "New link" (revoke,
   then create), members_update (role) and members_remove. Maps the API onto the shapes views/members.js renders. */
import { all, del, org, page, patch, post } from "../api.js";

/* The role enum (MemberUpdate.role) as menu options, each with what it may do, and the scopes each grants: the
   server's role map (auth/scopes.py ROLE_SCOPES), which the API does not serve. */
const ROLES = [
  { v: "owner", hint: "Everything, including the org itself and its owners" },
  { v: "admin", hint: "Everything except removing owners; manages members, catalog and tokens" },
  { v: "editor", hint: "Writes cases and plans; can't change products, features or members" },
  { v: "tester", hint: "Runs cycles and records results" },
  { v: "viewer", hint: "Reads everything in the org, changes nothing" }
];
const SCOPES_OF = {
  owner: "all scopes",
  admin: "all scopes · write:catalog",
  editor: "read · write:execution · write:cases · write:planning",
  tester: "read · write:execution",
  viewer: "read"
};
const roles = () => ROLES.map((r) => ({ role: r.v, desc: r.hint, scopes: SCOPES_OF[r.v] }));
const DAY = 86400000;

/* a time as "just now", "12 min ago", "1 h ago", "yesterday", "6 days ago" */
function ago(iso, now = Date.now()) {
  const min = Math.floor((now - new Date(iso).getTime()) / 60000);
  if (min < 2) return "just now";
  if (min < 60) return `${min} min ago`;
  if (min < 24 * 60) return `${Math.floor(min / 60)} h ago`;
  if (min < 48 * 60) return "yesterday";
  return `${Math.floor(min / (24 * 60))} days ago`;
}
/* last active: "now" within a minute or two (the server writes it at most once a minute), "" when never */
const active = (iso) => (!iso ? "" : ago(iso) === "just now" ? "now" : ago(iso));

/* invites_list and agents_list need admin: a member without it sees the members only (a role 403 shows less) */
const unlessForbidden = (none) => (e) => {
  if (e.status === 403) return none;
  throw e;
};

const member = (m, agents) => ({
  handle: m.actor_id, userId: m.user_id, email: m.email, role: m.role, active: active(m.last_active_at),
  agents: agents.filter((a) => a.owner_user_id === m.user_id && !a.disabled_at).length
});
const invite = (x, now = Date.now()) => ({
  id: x.id, email: x.email, role: x.role, invitedBy: x.invited_by_actor_id, when: ago(x.created_at, now),
  expiresIn: x.status === "expired" ? 0 : Math.max(0, Math.ceil((new Date(x.expires_at).getTime() - now) / DAY))
});
/* the accept view's link for a new invite: <app>?view=accept&token=<InviteCreated.token> */
export const inviteLink = (app, token) => `${app}?view=accept&token=${encodeURIComponent(token)}`;

/* params: the URL's query (q; id, a member's actor id, for change-role, role-changed, remove-confirm, removed)
   and ui, the hash's UI state. once: what a write just returned, which only the view that made it can show:
   { invite: InviteCreated, app: the app's URL } for invite-sent, or { draft: {email, role}, raw } for invite-error. */
export async function load(params, ctx, once = null) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  const q = (params.q || "").trim();
  const [hits, every, invites, agents] = await Promise.all([
    page(at("members"), { q, limit: 200 }),
    q ? page(at("members"), { limit: 1 }) : null,
    page(at("invites"), { limit: 200 }).catch(unlessForbidden({ items: [], total: 0 })),
    all(at("agents")).catch(unlessForbidden([]))
  ]);
  const members = hits.items.map((m) => member(m, agents));
  // the signed-in user's row (marked "you"); when q leaves it out, no row is theirs
  const me = hits.items.find((m) => m.user_id === ctx.user.handle);
  const data = {
    q, total: every ? every.total : hits.total, roles: roles(), me: me ? me.actor_id : ctx.user.handle,
    members, pending: invites.items.map((x) => invite(x)), pendingTotal: invites.total,
    draft: { email: "", role: "tester", error: "" },
    sel: null, open: null, openHl: null, roleChange: null, remove: null, removed: null, sent: null
  };
  if (once && once.invite) {
    const x = once.invite;
    data.sent = { email: x.email, role: x.role, link: inviteLink(once.app, x.token) };
    return { state: "invite-sent", data };
  }
  if (once && once.draft) {
    data.draft = { ...once.draft, error: once.raw };
    return { state: "invite-error", data };
  }
  const ui = params.ui || "";
  if (["pending", "invite-revoked"].includes(ui)) return { state: ui, data };
  if (ui === "invite-sent") return { state: "pending", data }; // the link was shown once; a reload can't show it again
  if (ui === "invite" || ui === "invite-error") return { state: "invite", data };
  const m = params.id && members.find((x) => x.handle === params.id);
  if (m && ui === "change-role") return { state: ui, data: { ...data, sel: m.handle, open: m.handle } };
  if (m && ui === "role-changed") return { state: ui, data: { ...data, sel: m.handle, roleChange: { handle: m.handle, role: m.role } } };
  if (m && ui === "remove-confirm") return { state: ui, data: { ...data, sel: m.handle, remove: { handle: m.handle } } };
  if (params.id && ui === "removed" && !m && ctx.people[params.id]) return { state: ui, data: { ...data, removed: params.id } };
  if (q) return { state: members.length ? "search" : "search-empty", data };
  return { state: "list", data };
}

/* The view's writes; each resolves to what the server returned. */
export const actions = {
  /* form: { email, role }; resolves to InviteCreated, whose token is shown once */
  invite: (form, ctx) => post(org(ctx.org.id, "invites"), { email: form.email, role: form.role }),
  /* a new link for a pending or expired invite: revoke it, then create one for the same email and role */
  async relink(inv, ctx) {
    await del(org(ctx.org.id, "invites", inv.id));
    return post(org(ctx.org.id, "invites"), { email: inv.email, role: inv.role });
  },
  revoke: (inviteId, ctx) => del(org(ctx.org.id, "invites", inviteId)),
  setRole: (userId, role, ctx) => patch(org(ctx.org.id, "members", userId), { role }),
  remove: (userId, ctx) => del(org(ctx.org.id, "members", userId))
};
