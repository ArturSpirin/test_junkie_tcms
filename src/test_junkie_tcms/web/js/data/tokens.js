/* Tokens and agents adapter (docs/app-api-contract.md §13): tokens_list, agents_list, members_list (agent owners)
   and actors_list (token owners' kind and name); the writes tokens_create (its secret is shown once), tokens_revoke,
   agents_create, agents_disable and agents_enable. Without admin the server lists only the caller's own tokens and
   refuses agents_list, so the view shows "My API tokens" only. Maps the API onto the shapes views/tokens.js renders. */
import { all, del, get, org, post } from "../api.js";
import { day } from "./map.js";

/* The scopes a token can carry, as toggle options with what each allows, and the ones each role may grant: the
   server's auth/scopes.py, which the API does not serve. */
const SCOPES = [
  { v: "read", hint: "Read catalog, cycles, results, reports" },
  { v: "write:catalog", hint: "Products, features, releases, tags" },
  { v: "write:planning", hint: "Test plans and cycles" },
  { v: "write:cases", hint: "Create and edit cases (new versions)" },
  { v: "write:execution", hint: "Record results, evidence, defects" },
  { v: "audit:read", hint: "Read the audit log" },
  { v: "admin", hint: "Members, roles, org settings" },
  { v: "tokens:self", hint: "Manage this user's own tokens" }
];
const EVERY = SCOPES.map((s) => s.v);
const ROLE_SCOPES = {
  viewer: ["read", "tokens:self"],
  tester: ["read", "write:execution", "tokens:self"],
  editor: ["read", "write:execution", "write:cases", "write:planning", "tokens:self"],
  admin: EVERY,
  owner: EVERY
};
const DAY = 86400000;
const EXPIRY_DAYS = [7, 30, 90, 365];
/* a token is "expiring" this many days before expires_at (the form's hint: owners get a warning 10 days before) */
const WARN_DAYS = 10;

/* "Fri Feb 12, 2027": the year only when it isn't this year */
const date = (iso, now = new Date()) => {
  const d = new Date(iso);
  return day(iso, { day: true }) + (d.getFullYear() === now.getFullYear() ? "" : `, ${d.getFullYear()}`);
};
/* "Fri Nov 13, 2:05 AM PST" */
const stamp = (iso) => `${date(iso)}, ${new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZoneName: "short" })}`;

function status(t, now = Date.now()) {
  if (t.revoked_at) return "revoked";
  if (!t.expires_at) return "active";
  const left = new Date(t.expires_at).getTime() - now;
  return left <= 0 ? "expired" : left <= WARN_DAYS * DAY ? "expiring" : "active";
}

/* agents_list needs admin: without it the view shows the caller's own tokens only (a role 403 shows less) */
const unlessForbidden = (e) => {
  if (e.status === 403) return null;
  throw e;
};

/* params: the URL's query (id: a token for revoke-confirm, an agent for agent-disabled; owner: the new token's
   owner, an agent id) and ui, the hash's UI state. once: what a write just returned, which only the view that
   made it can show: { token: TokenCreated, origin } for created, or { form, raw } for error-422. */
export async function load(params, ctx, once = null) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  const [rows, agentRows, memberRows, dir] = await Promise.all([
    all(at("tokens")),
    all(at("agents")).catch(unlessForbidden),
    all(at("members")),
    get(at("actors"))
  ]);
  const admin = agentRows !== null;
  const actors = Object.fromEntries(dir.actors.map((a) => [a.id, a]));
  const byUser = Object.fromEntries(memberRows.map((m) => [m.user_id, m]));
  const me = byUser[ctx.user.handle];
  const keyOf = Object.fromEntries(ctx.products.map((p) => [p.id, p.key]));
  const keys = (ids) => (ids || []).map((id) => keyOf[id] || id);
  const owner = (actorId) => {
    const a = actors[actorId];
    // a machine (consumer) holds the token its pairing issued: it shows as a token owner, by its name
    if (a && a.kind === "agent") return { kind: "agent", handle: a.name };
    if (a && a.kind === "consumer") return { kind: "consumer", handle: a.name };
    return { kind: "person", handle: actorId };
  };
  const tokens = rows.map((t) => {
    const s = status(t);
    return {
      id: t.id, name: t.name, prefix: `tjt_${t.prefix}`, owner: owner(t.actor_id), scopes: t.scopes, products: keys(t.product_ids),
      lastUsed: t.last_used_at ? stamp(t.last_used_at) : "never", expires: s === "revoked" ? "–" : t.expires_at ? date(t.expires_at) : "never", status: s
    };
  });
  const agents = (agentRows || []).map((a) => ({
    id: a.id, name: a.name, desc: a.description || "", owner: byUser[a.owner_user_id] ? byUser[a.owner_user_id].actor_id : a.owner_user_id,
    role: a.role, tokens: rows.filter((t) => t.actor_id === a.id && !t.revoked_at).length,
    lastActive: a.last_active_at ? stamp(a.last_active_at) : "never", status: a.disabled_at ? "disabled" : "active"
  }));
  const now = Date.now();
  const myHandle = me ? me.actor_id : ctx.user.handle;
  const data = {
    baseUrl: "", roleAs: null, scopes: SCOPES.map((s) => ({ scope: s.v, desc: s.hint })), roleScopes: ROLE_SCOPES, tokens, agents,
    products: ctx.products.map((p) => ({ key: p.key, name: p.name, markCls: p.markCls })),
    expiryDates: Object.fromEntries(EXPIRY_DAYS.map((n) => [n, date(new Date(now + n * DAY).toISOString())])),
    draft: { name: "", owner: admin && agents.some((a) => a.id === params.owner) ? params.owner : "me", on: ["read"], products: [], expiry: "90" },
    owners: memberRows.map((m) => ({ handle: m.actor_id, userId: m.user_id, role: m.role })),
    agentDraft: { name: "", owner: myHandle, desc: "", role: "viewer" },
    created: null, revoke: null, disabled: null, ownerOpen: false,
    self: admin ? null : myHandle,
    error: null
  };
  if (once && once.token) {
    const c = once.token;
    data.baseUrl = once.origin;
    data.created = { secret: c.token, prefix: `tjt_${c.prefix}`, scopes: c.scopes, products: keys(c.product_ids), expires: c.expires_at ? date(c.expires_at) : "never" };
    return { state: "created", data };
  }
  if (once && once.raw) {
    const f = once.form;
    const agent = f.owner !== "me" && agents.find((a) => a.id === f.owner);
    const ownerRole = agent ? agent.role : ctx.user.role;
    const bad = f.scopes.find((s) => !ROLE_SCOPES[ownerRole].includes(s)) || null;
    data.draft = { ...data.draft, name: f.name, owner: f.owner, on: f.scopes, products: f.products, expiry: f.expiry };
    data.error = { owner: agent ? agent.name : (ctx.people[myHandle] || [myHandle])[0], ownerRole, on: f.scopes, bad, raw: once.raw };
    return { state: "error-422", data };
  }
  const ui = params.ui || "";
  if (ui === "create" || ui === "create-owner-open") return { state: ui, data: { ...data, ownerOpen: ui === "create-owner-open" } };
  const tok = params.id && tokens.find((t) => t.id === params.id);
  if (ui === "revoke-confirm" && tok && tok.status !== "revoked") return { state: ui, data: { ...data, revoke: tok.id } };
  if (ui === "revoked") return { state: ui, data };
  if (!admin) return { state: "self-only", data };
  if (ui === "agents" || ui === "create-agent") return { state: ui, data };
  const agent = params.id && agents.find((a) => a.id === params.id);
  if (ui === "agent-disabled" && agent && agent.status === "disabled") return { state: ui, data: { ...data, disabled: agent.id } };
  return { state: ui === "agent-disabled" ? "agents" : "tokens", data };
}

/* The view's writes; each resolves to what the server returned. */
export const actions = {
  /* form: { name, owner ("me" or an agent id), scopes, products (keys; none = all), expiry ("7", "30", "90",
     "365" days, or "never") }; resolves to TokenCreated, whose token (the secret) is shown once */
  create(form, ctx) {
    if (!(form.expiry === "never" || EXPIRY_DAYS.includes(Number(form.expiry)))) throw new Error(`Expiry "${form.expiry}" can't be sent: pick a number of days or never.`);
    const ids = Object.fromEntries(ctx.products.map((p) => [p.key, p.id]));
    return post(org(ctx.org.id, "tokens"), {
      name: form.name, scopes: form.scopes,
      actor_id: form.owner && form.owner !== "me" ? form.owner : undefined,
      product_ids: form.products.length ? form.products.map((k) => ids[k] || k) : undefined,
      expires_at: form.expiry === "never" ? undefined : new Date(Date.now() + Number(form.expiry) * DAY).toISOString()
    });
  },
  revoke: (tokenId, ctx) => del(org(ctx.org.id, "tokens", tokenId)),
  /* form: { name, ownerUserId, desc, role }; resolves to AgentOut */
  createAgent: (form, ctx) => post(org(ctx.org.id, "agents"), { name: form.name, role: form.role, description: form.desc || undefined, owner_user_id: form.ownerUserId }),
  disable: (agentId, ctx) => post(org(ctx.org.id, "agents", agentId, "disable")),
  enable: (agentId, ctx) => post(org(ctx.org.id, "agents", agentId, "enable"))
};
