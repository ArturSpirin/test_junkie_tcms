/* Case version history adapter (docs/app-api-contract.md §6): cases_get, cases_versions_list (with via, token
   and on-behalf-of per version), cases_version_get for the two picked versions (the compare is drawn from the two
   gets), actors_list and members_list for names, cases_cycles (the pinned version per cycle) with cycles_get and
   releases_list for each cycle's release, and features_list for the crumbs. Write: cases_restore with If-Match.
   URL: ?view=versions&id=<case key or id>&a=<from>&b=<to>#<ui>; ui is "compare", "restore-confirm", "restored"
   or "used-in-cycles". Maps the API onto the shapes views/versions.js renders. */
import { all, get, org, post } from "../api.js";
import { flatten } from "./map.js";

const UI_STATES = ["restore-confirm", "restored", "used-in-cycles"];

/* "Thu Nov 12, 3:14 PM" in the browser's zone */
const at = (iso) => new Date(iso).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).replace(/^(\w+),/, "$1");
/* a rich field as served (rich=markdown: a string or { markdown }) as its Markdown */
const text = (v) => (typeof v === "string" ? v : (v && v.markdown) || "");
const oneLine = (s) => text(s).replace(/\s+/g, " ").trim();

/* ---------- word diff: the "to" side as text, del (removed) and ins (added) runs ---------- */
function words(a, b) {
  const x = a.split(/(\s+)/).filter(Boolean), y = b.split(/(\s+)/).filter(Boolean);
  const n = x.length, m = y.length;
  const L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  const push = (k, s) => { const last = out[out.length - 1]; if (last && last[k] !== undefined) last[k] += s; else out.push({ [k]: s }); };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { push("text", x[i]); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) push("del", x[i++]); else push("ins", y[j++]);
  }
  while (i < n) push("del", x[i++]);
  while (j < m) push("ins", y[j++]);
  return out;
}

/* the fields a version holds, as one comparable string each, in the order the compare lists them */
const FIELDS = [
  ["Title", (v) => v.title], ["Description", (v) => text(v.description)], ["Preconditions", (v) => text(v.preconditions)],
  ["Priority", (v) => v.priority], ["Type", (v) => v.type], ["Status", (v) => v.status], ["Automation", (v) => v.automation],
  ["Automation ref", (v) => v.automation_ref || ""], ["Tags", (v) => v.tags.join(", ")],
  ["Links", (v) => v.links.map((l) => (l.key ? `${l.key} ${l.url}` : l.url)).join(", ")],
  ["Custom fields", (v) => (Object.keys(v.custom || {}).length ? JSON.stringify(v.custom) : "")]
];

/* What changed from version A to version B: field edits, step edits (by step id), added and removed steps,
   steps whose order changed, the two change notes, and what stayed the same. */
function compare(A, B) {
  const fields = [], same = [];
  const change = (label, from, to) => fields.push({ label, from: from ? [{ text: from }] : [], to: words(from, to) });
  for (const [label, get] of FIELDS) {
    const f = get(A), t = get(B);
    if (f === t) same.push(label.toLowerCase());
    else change(label, f, t);
  }
  const bA = Object.fromEntries(A.steps.map((s) => [s.id, s])), bB = Object.fromEntries(B.steps.map((s) => [s.id, s]));
  const sameSteps = [];
  for (const s of B.steps) {
    const o = bA[s.id];
    if (!o) { fields.push({ label: `Step ${s.id} · added`, from: [], to: [{ ins: `${oneLine(s.action)} → ${oneLine(s.expected)}` }] }); continue; }
    let edited = false;
    for (const k of ["action", "expected"]) {
      if (text(o[k]) !== text(s[k])) { change(`Step ${s.id} · ${k}`, text(o[k]), text(s[k])); edited = true; }
    }
    if (!edited) sameSteps.push(s.id);
  }
  for (const s of A.steps) if (!bB[s.id]) fields.push({ label: `Step ${s.id} · removed`, from: [{ text: `${oneLine(s.action)} → ${oneLine(s.expected)}` }], to: [{ del: `${oneLine(s.action)} → ${oneLine(s.expected)}` }] });
  /* a step whose place among the steps both versions hold changed; from and to are its numbers in each version */
  const kept = (list, other) => list.filter((s) => other[s.id]).map((s) => s.id);
  const ka = kept(A.steps, bB), kb = kept(B.steps, bA);
  const moves = kb.filter((id, i) => ka.indexOf(id) !== i).map((id) => ({
    step: id, title: oneLine(bB[id].action), from: A.steps.findIndex((s) => s.id === id) + 1, to: B.steps.findIndex((s) => s.id === id) + 1
  }));
  const unchanged = [...same, ...(sameSteps.length ? [`step${sameSteps.length > 1 ? "s" : ""} ${sameSteps.join(", ")}`] : [])];
  return {
    moves, fields,
    note: { from: A.change_note || "", to: B.change_note || "" },
    unchanged: unchanged.length ? unchanged.join(", ").replace(/^./, (c) => c.toUpperCase()) : "Nothing"
  };
}

/* a CaseVersionSummary as a history row. kind: agent (an agent actor), token (saved with an API token), else
   person; who: the actor id a person is looked up by (ctx.people), the agent's or the token's name */
function row(v, dir, members) {
  const a = dir.actors.find((x) => x.id === v.created_by_actor_id);
  const t = v.token_id ? dir.tokens.find((x) => x.id === v.token_id) : null;
  const kind = a && a.kind === "agent" ? "agent" : t ? "token" : "person";
  const who = kind === "agent" ? a.name : kind === "token" ? t.name : v.created_by_actor_id;
  const behalf = v.on_behalf_of_user_id ? members.find((m) => m.user_id === v.on_behalf_of_user_id) : null;
  return {
    n: v.version, kind, who, via: v.via || "", at: at(v.created_at), note: v.change_note || "",
    forWho: v.on_behalf_of_user_id ? (behalf ? behalf.name : v.on_behalf_of_user_id) : ""
  };
}

/* a cycle the case is in: its release, the version it pinned and that case's result there */
function used(x, cycles, releases, current) {
  const cy = cycles[x.cycle_id];
  const open = x.cycle_status !== "closed";
  const note = !open ? "closed" : x.case_version === current ? "current"
    : x.status !== "untested" ? `has a result: can refresh to v${current}` : `untested: can refresh to v${current}`;
  return { id: x.cycle_id, cycle: x.name, release: cy && cy.release_id ? releases[cy.release_id] || "" : "", pinned: x.case_version, result: x.status, note, open };
}

/* params: the URL's query (id: the case key or id; a, b: the versions to compare) and ui, the hash's UI state */
export async function load(params, ctx) {
  if (!params.id) throw new Error("Open a case's history from the case: no case was given.");
  const path = (...rest) => org(ctx.org.id, ...rest);
  const c = await get(path("cases", params.id));
  const product = ctx.products.find((p) => p.id === c.product_id) || ctx.product;
  const [list, dir, cyc, tree, rels] = await Promise.all([
    all(path("cases", c.id, "versions")),
    get(path("actors")),
    get(path("cases", c.id, "cycles")),
    get(path("products", product.key, "features")),
    all(path("products", product.key, "releases"))
  ]);
  const cur = c.current_version;
  const num = (v, d) => { const n = Number(v); return Number.isInteger(n) && n >= 1 && n <= cur ? n : d; };
  const b = num(params.b, cur);
  const a = num(params.a, Math.max(1, b - 1));
  const members = list.some((v) => v.on_behalf_of_user_id) ? await all(path("members")) : [];
  const [A, B, ...cycles] = await Promise.all([
    get(path("cases", c.id, "versions", String(a))),
    get(path("cases", c.id, "versions", String(b))),
    ...[...new Set(cyc.map((x) => x.cycle_id))].map((id) => get(path("cycles", id)))
  ]);
  const byCycle = Object.fromEntries(cycles.map((x) => [x.id, x]));
  const releases = Object.fromEntries(rels.map((r) => [r.id, r.version]));
  const feature = flatten(tree.items).find((f) => f.id === c.feature_id);
  const data = {
    case: { id: c.id, key: c.key, title: c.title, product: product.name, productKey: product.key, feature: feature ? feature.name : "", featureId: c.feature_id, version: cur },
    pick: { a, b },
    versions: list.map((v) => row(v, dir, members)),
    diff: compare(A, B),
    used: cyc.map((x) => used(x, byCycle, releases, cur)),
    draft: { note: `Restored v${a}` }
  };
  if (UI_STATES.includes(params.ui)) return { state: params.ui, data };
  /* two versions picked in the URL other than the latest two: a compare */
  if ((params.a || params.b) && !(b === cur && a === Math.max(1, cur - 1))) return { state: "compare", data };
  return { state: "default", data };
}

/* The view's write; it resolves to the server's CaseOut, at its new version. */
export const actions = {
  /* cases_restore: copies version into a new version; current is the case's version as loaded (If-Match) */
  restore: (caseId, version, note, current, ctx) => post(org(ctx.org.id, "cases", caseId, "restore"), { version, change_note: note || null }, { ifMatch: current })
};
