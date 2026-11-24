/* Audit log adapter (docs/app-api-contract.md §14): audit_list with its filters (actor_id, actor_kind, action, via,
   entity_type, entity_id, since, until and q are the server's), audit_retention, actors_list for names,
   agents_list and members_list for the actor filter, and cases_get for a case's key and title.
   Maps the API onto the shapes views/audit.js renders. */
import { all, get, org, page } from "../api.js";
import { day } from "./map.js";

const PAGE = 50;
const RANGES = { today: 0, "7d": 6, "14d": 13, "30d": 29 };
const KINDS = ["person", "agent", "token", "consumer"];
/* the actor filter's kinds as audit_list's actor_kind */
const ACTOR_KIND = { person: "user", agent: "agent", token: "token", consumer: "consumer" };
/* the directory's actor kinds as the view's */
const KIND = { user: "person", agent: "agent", consumer: "consumer" };
/* object types the view names differently from the API's entity_type */
const TYPE = { case: "test_case" };
const typeLabel = (t) => Object.keys(TYPE).find((k) => TYPE[k] === t) || t;

const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const midnight = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const daysAgo = (n) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - n); return d; };
const clock = (iso) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZoneName: "short" });

/* the period as audit_list's since (inclusive) and until (exclusive), from ?range= or ?range=custom&from=&to= */
function period(params, fallback) {
  const value = params.range in RANGES || params.range === "custom" ? params.range : fallback;
  if (value === "custom" && params.from) {
    const to = params.to || isoDay(new Date());
    const end = midnight(to);
    end.setDate(end.getDate() + 1);
    return { range: { value, applied: true, from: params.from, to }, since: midnight(params.from).toISOString(), until: end.toISOString() };
  }
  const v = value === "custom" ? fallback : value;
  return { range: { value: v }, since: daysAgo(RANGES[v]).toISOString(), until: undefined };
}

/* a change as [before, after]: the API writes [before, after], {from, to}, or a plain value (a create) */
function pair(v) {
  if (Array.isArray(v) && v.length === 2) return v;
  if (v && typeof v === "object" && !Array.isArray(v) && "from" in v && "to" in v) return [v.from, v.to];
  return [null, v];
}
const shown = (v) => (v === null || v === undefined ? "" : Array.isArray(v) ? v.map((x) => (x && typeof x === "object" ? JSON.stringify(x) : x)) : typeof v === "object" ? JSON.stringify(v) : v);

function event(a, names) {
  const who = names.actors[a.actor_id];
  const kind = who ? KIND[who.kind] || "person" : "person";
  const changes = Object.entries(a.changes || {}).filter(([k]) => k !== "entity_version").map(([field, v]) => {
    const [before, after] = pair(v);
    return { field, before: shown(before), after: shown(after) };
  });
  const version = a.changes && a.changes.entity_version ? pair(a.changes.entity_version)[1] || 0 : 0;
  const c = a.entity_type === "test_case" ? names.cases[a.entity_id] : null;
  return {
    eid: a.id, day: day(a.created_at, { day: true }), time: clock(a.created_at),
    actor: { kind, id: a.actor_id, name: who ? who.name : a.actor_id },
    token: a.token_id ? (names.tokens[a.token_id] || a.token_id) : "",
    onBehalfOf: a.on_behalf_of_user_id ? names.users[a.on_behalf_of_user_id] || a.on_behalf_of_user_id : "",
    via: a.via, action: a.action, type: typeLabel(a.entity_type), id: c ? c.key : a.entity_id, entityId: a.entity_id,
    version, summary: changes.map((x) => x.field).join(", "),
    detail: { at: a.created_at, requestId: a.request_id || "", tool: a.tool || "", changes },
    raw: a
  };
}

/* the audit_list query for the URL's filters */
function query(params, p) {
  const actor = params.actor || "any";
  const q = {
    since: p.since, until: p.until, q: (params.q || "").trim(),
    action: params.action && params.action !== "any" ? params.action : undefined,
    via: params.via && params.via !== "any" ? params.via : undefined,
    entity_type: params.type && params.type !== "any" ? TYPE[params.type] || params.type : undefined,
    entity_id: params.entity || undefined
  };
  if (ACTOR_KIND[actor]) q.actor_kind = ACTOR_KIND[actor];
  else if (actor !== "any") q.actor_id = actor.replace(/^agent:/, "");
  return q;
}

/* params: the URL's query (actor, action, via, type, entity, q, range, from, to, open) and ui ("filter-open"). */
export async function load(params, ctx) {
  const at = (...rest) => org(ctx.org.id, ...rest);
  const p = period(params, params.entity ? "30d" : "7d");
  const [rows, retention, directory, agents, members] = await Promise.all([
    page(at("audit"), { ...query(params, p), limit: PAGE }),
    get(at("audit", "retention")),
    get(at("actors")),
    all(at("agents")),
    all(at("members"))
  ]);
  const caseIds = [...new Set(rows.items.filter((a) => a.entity_type === "test_case").map((a) => a.entity_id))];
  if (params.entity && params.type === "case" && !caseIds.includes(params.entity)) caseIds.push(params.entity);
  const cases = Object.fromEntries(await Promise.all(caseIds.map(async (id) => [id, await get(at("cases", id))])));
  const users = Object.fromEntries(members.map((m) => [m.user_id, m.actor_id]));
  const names = {
    actors: Object.fromEntries(directory.actors.map((a) => [a.id, a])),
    tokens: Object.fromEntries(directory.tokens.map((t) => [t.id, t.name])),
    users, cases
  };
  const events = rows.items.map((a) => event(a, names));
  const actor = params.actor || "any";
  const named = actor.replace(/^agent:/, "");
  const actorLabel = KINDS.includes(actor) || actor === "any" ? actor : (names.actors[named] || { name: named }).name;
  const filter = {
    actor, actorLabel, action: params.action || "any", via: params.via || "any", type: params.type || "any",
    entityId: params.entity || "", entityLabel: params.entity && cases[params.entity] ? cases[params.entity].key : params.entity || "",
    q: (params.q || "").trim(), viaOpen: params.ui === "filter-open", range: p.range
  };
  const data = {
    retention: { days: retention.days, oldest: retention.oldest_kept ? day(retention.oldest_kept, { day: true }) : "", oldestDay: retention.oldest_kept ? isoDay(new Date(retention.oldest_kept)) : "" },
    agents: agents.map((a) => ({ id: a.id, name: a.name, owner: users[a.owner_user_id] || a.owner_user_id, role: a.role })),
    members: members.filter((m) => !m.removed_at).map((m) => ({ handle: m.actor_id, role: m.role })),
    filter, events, total: rows.total, open: events.findIndex((e) => e.eid === params.open), entity: null
  };
  if (params.entity) {
    const c = cases[params.entity];
    data.entity = { type: filter.type === "any" ? "" : filter.type, id: c ? c.key : params.entity, key: c ? c.key : "", title: c ? c.title : "" };
    return { state: "entity", data };
  }
  if (!events.length) return { state: "empty", data };
  if (params.ui === "filter-open") return { state: "filter-open", data };
  if (data.open >= 0) return { state: "expanded", data };
  if (p.range.from && data.retention.oldestDay && p.range.from < data.retention.oldestDay) return { state: "retention", data };
  const filtered = actor !== "any" || filter.action !== "any" || filter.via !== "any" || filter.type !== "any" || filter.q || p.range.value !== "7d";
  return { state: filtered ? "filtered-agent" : "default", data };
}

/* The view's reads beyond the page: export resolves to every AuditOut the current filters match. */
export const actions = {
  export: (params, ctx) => all(org(ctx.org.id, "audit"), query(params, period(params, params.entity ? "30d" : "7d")))
};
