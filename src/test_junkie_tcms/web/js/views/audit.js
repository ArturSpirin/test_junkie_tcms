/* Audit log: every write with its actor, on-behalf-of person, token and channel; filters, one expanded event, one entity's history, retention.
   The data is data/audit.js; every filter is a query parameter the server applies. */
import { I, ver, actor, dd, dr, toast, esc, person } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/audit.js";

const who = (a) => a.kind === "person" ? actor("person", a.id, { k: true })
  : a.kind === "consumer" ? `<span class="actor"><span class="av token">${I.server}</span><span>${esc(a.name)}</span><span class="kind">machine</span></span>`
  : actor(a.kind, esc(a.name), { k: true });
/* the URL's filters, so a link keeps them; over replaces some (null drops one) */
const keep = (d, over = {}) => {
  const f = d.filter, r = f.range;
  const v = (x) => (x === "any" ? null : x);
  return { actor: v(f.actor), action: v(f.action), via: v(f.via), type: v(f.type), entity: f.entityId || null, q: f.q || null,
    range: r.value, from: r.value === "custom" ? r.from : null, to: r.value === "custom" ? r.to : null, ...over };
};
const entHref = (d, e) => href("audit", { ...keep(d, { open: null }), type: e.type, entity: e.entityId });
const ent = (d, e) => `<span class="faint" style="font-size:12px">${esc(e.type)}</span> ${e.type === "case" || e.type === "cycle_case" ? `<a class="key" href="${entHref(d, e)}">${esc(e.id)}</a>` : `<span class="${e.type === "token" ? "mono" : ""}">${esc(e.id)}</span>`}${e.version ? " " + ver(e.version, e.type === "cycle_case") : ""}`;
const forLine = (e) => (e.onBehalfOf ? `<div class="for">${I.person.replace(/16/g, "13")}<span>for ${esc(person(e.onBehalfOf)[0])}</span></div>` : "") + (e.token && e.actor.kind !== "token" ? `<div class="for">${I.key.replace(/16/g, "13")}<span class="mono">${esc(e.token)}</span></div>` : "");

/* filter option sets: the fixed kinds, actions, channels and object types; agents and people come from data */
const actorOptions = (d) => [{ group: "Kind" }, { v: "any", label: "Any actor", icon: I.filter }, { v: "person", label: "People", icon: I.person, hint: "signed-in members" }, { v: "agent", label: "Agents", icon: I.agent, hint: "non-human members" }, { v: "token", label: "Tokens", icon: I.key, hint: "a member through a token" }, { v: "consumer", label: "Machines", icon: I.server, hint: "paired consumers" },
  { group: "Agents" }, ...d.agents.map((a) => ({ v: `agent:${a.id}`, label: a.name, short: `${a.name} (agent)`, icon: I.agent, hint: `owner ${person(a.owner)[0].split(" ")[0]} · ${a.role}` })),
  { group: "People" }, ...d.members.map((m) => ({ v: m.handle, label: person(m.handle)[0], icon: I.person, hint: m.role }))];
/* action names are the API's, singular (docs/app-api-contract.md §14) */
const O_ACTION = [{ v: "any", label: "Any action", icon: I.filter }, { group: "Cases" }, { v: "case.create", label: "case.create" }, { v: "case.update", label: "case.update", hint: "new version" }, { v: "case.restore", label: "case.restore" }, { v: "case.import", label: "case.import" }, { v: "case.move", label: "case.move" },
  { group: "Cycles and results" }, { v: "cycle_batch.create", label: "cycle_batch.create" }, { v: "cycle_case.refresh_version", label: "cycle_case.refresh_version", hint: "pinned version moved" }, { v: "cycle.close", label: "cycle.close" }, { v: "result.create", label: "result.create" },
  { group: "Access" }, { v: "token.create", label: "token.create" }, { v: "token.revoke", label: "token.revoke", danger: true }, { v: "agent.create", label: "agent.create" }, { v: "agent.disable", label: "agent.disable", danger: true }];
/* audit_list's via is ui, api or mcp */
const O_VIA = [{ v: "any", label: "Any channel", icon: I.filter }, "-", { v: "ui", label: "ui", icon: I.person, hint: "browser session (cookie + CSRF)" }, { v: "api", label: "api", icon: I.link, hint: "REST with a bearer token" }, { v: "mcp", label: "mcp", icon: I.mcp, hint: "MCP tool call" }];
const O_TYPE = [{ v: "any", label: "Any object", icon: I.filter }, "-", { v: "case", label: "case", icon: I.doc }, { v: "cycle_case", label: "cycle_case", icon: I.run }, { v: "cycle", label: "cycle", icon: I.cycle }, { v: "release", label: "release", icon: I.tag }, { v: "feature", label: "feature", icon: I.folder }, { v: "token", label: "token", icon: I.key }, { v: "agent", label: "agent", icon: I.agent }];

const day = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
function filters(d) {
  const f = d.filter;
  const x = (over) => ` <a class="x" href="${href("audit", keep(d, { open: null, ...over }))}" aria-label="Clear">${I.x}</a>`;
  const chips = [f.actor !== "any" ? `<span class="chip acc">actor: ${esc(f.actorLabel)}${x({ actor: null })}</span>` : "", f.entityId ? `<span class="chip acc">${esc(f.type)} ${esc(f.entityLabel)}${x({ type: null, entity: null })}</span>` : ""].join("");
  const range = f.range.from ? Object.assign({}, f.range, { from: day(f.range.from), to: day(f.range.to || d.ctx.today) }) : f.range;
  return `<div class="afbar" role="search" aria-label="Filter events">
  <label class="in-ic">${I.search}<input class="in" placeholder="Search summary, entity id, request_id" aria-label="Search events" value="${esc(f.q || "")}"></label>
  ${dd({ value: f.actor, options: actorOptions(d), cls: "sm", pre: "Actor", search: "Find an actor…", name: "actor", label: "Actor" })}
  ${dd({ value: f.action, options: O_ACTION, cls: "sm", pre: "Action", search: "Find an action…", name: "action", label: "Action" })}
  ${dd({ value: f.via, options: O_VIA, cls: "sm", pre: "Via", name: "via", label: "Via", open: !!f.viaOpen, hl: f.viaOpen ? "mcp" : undefined })}
  ${dd({ value: f.type, options: O_TYPE, cls: "sm", pre: "Object", name: "type", label: "Object type" })}
  ${dr(range)}
  </div>
  <div class="afmeta">${chips}<span>${d.total === d.events.length ? `${d.total} events` : `${d.events.length} of ${d.total} events`}</span></div>`;
}
const diffVal = (v, tag) => Array.isArray(v) ? esc(JSON.stringify(v)) : `<${tag}>${esc(v)}</${tag}>`;
/* a list change shows the old list as is and marks the added items in the new one */
const diffAfter = (c) => Array.isArray(c.after) ? `[${c.after.map((x) => (Array.isArray(c.before) && c.before.includes(x) ? esc(JSON.stringify(x)) : `<ins>${esc(JSON.stringify(x))}</ins>`)).join(", ")}]` : `<ins>${esc(c.after)}</ins>`;
function detail(d, e) {
  const x = e.detail || { changes: [] };
  const history = e.type === "case" ? `<a class="btn sm" href="${href("versions", { id: e.id })}">${I.restore}Open ${esc(e.id)} history</a>` : "";
  return `<div class="xpanel">
  <div class="row wrap"><span class="eyebrow">Event</span><span class="act">${esc(e.action)}</span><span class="via">${esc(e.via)}</span><span class="faint" style="font-size:12px;margin-left:auto">${esc(e.day)}, ${esc(e.time)}${x.at ? ` · ${esc(x.at)}` : ""}</span></div>
  <div class="kv">
    <div><span class="eyebrow">actor</span><div class="v">${who(e.actor)}</div></div>
    <div><span class="eyebrow">on_behalf_of_user</span><div class="v">${e.onBehalfOf ? actor("person", e.onBehalfOf) : "–"}</div></div>
    <div><span class="eyebrow">token_id</span><div class="v mono">${esc(e.token || "– (session)")}</div></div>
    <div><span class="eyebrow">request_id</span><div class="v mono">${esc(x.requestId || "–")}</div></div>
    <div><span class="eyebrow">entity</span><div class="v">${esc(e.type)} <span class="mono">${esc(e.id)}</span></div></div>
    <div><span class="eyebrow">entity_version</span><div class="v">${e.version ? ver(e.version) : "–"}</div></div>
    <div><span class="eyebrow">tool</span><div class="v mono">${e.via === "mcp" && x.tool ? esc(x.tool) : "–"}</div></div>
    <div><span class="eyebrow">outbox</span><div class="v muted">written, not consumed (v1)</div></div>
  </div>
  <div class="eyebrow" style="color:var(--faint);margin-bottom:8px">Changes · before → after</div>
  <div class="chg diff">
${x.changes.map((c) => `    <div class="drow"><span class="f">${esc(c.field)}</span><div>${diffVal(c.before, "del")}</div><div>${diffAfter(c)}</div></div>`).join("\n")}</div>
  <div class="acts">${history}<a class="btn sm ghost" href="${entHref(d, e)}">All events for ${esc(e.id)}</a><span class="sp"></span><button class="btn sm ghost" data-copy>${I.copy}Copy as JSON</button></div></div>`;
}
function table(d) {
  const list = d.events, open = d.open;
  const go = (e, i) => href("audit", keep(d, { open: i === open ? null : e.eid }));
  const row = (e, i) => `<tr class="ev${i === open ? " open" : ""}" data-go="${esc(go(e, i))}" aria-expanded="${i === open}"><td class="when"><b>${esc(e.time)}</b><span>${esc(e.day)}</span></td><td>${who(e.actor)}${forLine(e)}</td><td><span class="act">${esc(e.action)}</span></td><td>${ent(d, e)}</td><td><span class="via">${esc(e.via)}</span></td><td class="hide-m muted" style="font-size:13px">${esc(e.summary)}</td><td style="width:36px"><span class="cv">${I.chev}</span></td></tr>` + (i === open ? `<tr class="xrow"><td colspan="7">${detail(d, e)}</td></tr>` : "");
  const mrow = (e, i) => `<div class="it${i === open ? " open" : ""}" data-go="${esc(go(e, i))}"><div class="row"><span class="act">${esc(e.action)}</span><span class="via">${esc(e.via)}</span><span class="faint" style="font-size:12px;margin-left:auto">${esc(e.day.replace(/^\w+ /, ""))}, ${esc(e.time)}</span></div><div>${who(e.actor)}${forLine(e)}</div><div>${ent(d, e)}</div>${i === open ? detail(d, e) : ""}</div>`;
  return `<div class="card"><div class="tbl-wrap mswap cue"><table class="t atbl"><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Object</th><th>Via</th><th class="hide-m">Summary</th><th></th></tr></thead><tbody>${list.map(row).join("")}</tbody></table></div><div class="mlist">${list.map(mrow).join("")}</div></div>`;
}
const head = (d, h1 = "Audit log", crumbs = "") => `<div class="crumbs"><span>${esc(d.ctx.org.name)}</span><span class="sep">/</span>${crumbs || "<span>Audit log</span>"}</div>
<div class="ph"><div><div class="eyebrow">Append-only</div><h1>${h1}</h1></div><div class="actions"><button class="btn" data-export>${I.upload}Export CSV</button></div></div>
<p class="sub muted" style="margin-top:-10px;margin-bottom:20px">Every write, by a person, an agent or a token, with the person it acted for and the channel it came through. Kept ${d.retention.days} days; read needs <span class="mono">audit:read</span>.</p>`;
/* the policy is stated, not enforced yet: nothing deletes audit rows (docs/app-api-contract.md §14) */
const retention = (d) => `<div class="banner info" style="margin-top:16px">${I.info}<div>The policy keeps events ${d.retention.days} days${d.retention.oldest ? `; the oldest kept is from ${esc(d.retention.oldest)}` : ""}. Nothing is deleted yet. Case versions and results are kept either way. Export CSV to keep a copy.</div></div>`;
const log = (d) => head(d) + filters(d) + table(d);

const entity = (d) => {
  const n = d.entity;
  return head(d, esc(n.title ? `${n.id} · ${n.title}` : n.id), `<a href="${href("audit")}">Audit log</a><span class="sep">/</span><span>${esc(`${n.type} ${n.id}`.trim())}</span>`) + filters(d) + table(d);
};
const empty = (d) => head(d) + filters(d) + `<div class="card"><div class="empty"><div class="ill">${I.audit}</div><h3>No events match</h3><p style="margin:0">${d.filter.actor !== "any" ? `${esc(d.filter.actorLabel)} has done nothing in this period.` : "Nothing was written in this period."} Widen the period or clear a filter.</p><a class="btn" href="${href("audit")}">Clear filters</a></div></div>`;
const expired = (d) => log(d) +
  `<div class="card" style="margin-top:16px"><div class="empty" style="padding:32px 16px"><div class="ill">${I.lock}</div><h3>No older events</h3><p style="margin:0">The oldest event kept is from ${esc(d.retention.oldest)}.</p></div></div>` + retention(d);

/* the custom range the date picker applied: a preset, else the two days picked on its calendars */
const pad = (n) => String(n).padStart(2, "0");
const isoOf = (dt) => `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
function picked(w) {
  const pre = w.querySelector(".dr-pre button.on");
  const now = new Date();
  const at = (y, m, dd) => isoOf(new Date(y, m, dd));
  if (pre) {
    const k = pre.dataset.pre;
    if (["today", "7d", "14d", "30d"].includes(k)) return { range: k };
    if (k === "y") return { range: "custom", from: at(now.getFullYear(), now.getMonth(), now.getDate() - 1), to: at(now.getFullYear(), now.getMonth(), now.getDate() - 1) };
    if (k === "m") return { range: "custom", from: at(now.getFullYear(), now.getMonth(), 1), to: isoOf(now) };
    if (k === "lm") return { range: "custom", from: at(now.getFullYear(), now.getMonth() - 1, 1), to: at(now.getFullYear(), now.getMonth(), 0) };
  }
  const cell = (el) => { const [y, m, dd] = el.dataset.day.split("-").map(Number); return at(y, m - 1, dd); };
  const a = w.querySelector(".cal-g .d.a"), b = w.querySelector(".cal-g .d.b") || a;
  return a ? { range: "custom", from: cell(a), to: cell(b) } : null;
}

/* the real controls: every filter, the search (Enter) and the period go to the server through the URL; a row
   opens its event; Copy as JSON copies the event the API returned; Export CSV writes every matching event */
let cur = null;
let wired = false;
function wireDocument() {
  if (wired) return;
  wired = true;
  document.addEventListener("dr:change", (e) => {
    const main = document.querySelector('[data-view="audit"]');
    if (!cur || !main) return;
    const w = main.querySelector("[data-drw]");
    const to = e.detail.value === "custom" ? picked(w) : { range: e.detail.value, from: null, to: null };
    if (to) location.assign(href("audit", keep(cur, { open: null, from: null, to: null, ...to })));
  });
}
const csvCell = (v) => { const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const COLS = ["id", "created_at", "actor_id", "token_id", "on_behalf_of_user_id", "via", "action", "entity_type", "entity_id", "request_id", "tool", "changes"];
function after(main, state, d) {
  cur = d;
  wireDocument();
  main.querySelectorAll("[data-go]").forEach((g) => g.addEventListener("click", (e) => { if (!e.target.closest("a, button, .xpanel")) location.assign(g.dataset.go); }));
  const bar = main.querySelector(".afbar");
  if (bar) bar.addEventListener("dd:change", (e) => location.assign(href("audit", keep(d, { open: null, [e.detail.name]: e.detail.value === "any" ? null : e.detail.value }))));
  const box = main.querySelector(".afbar input.in");
  if (box) box.addEventListener("keydown", (e) => { if (e.key === "Enter") location.assign(href("audit", keep(d, { open: null, q: box.value.trim() || null }))); });
  const copy = main.querySelector("[data-copy]");
  if (copy) copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(d.events[d.open].raw, null, 2));
      toast('<b>Copied.</b> <span class="muted">Event as JSON</span>');
    } catch (e) {
      showError(main.querySelector(".xpanel"), e, "Couldn't copy the event.");
    }
  });
  const exp = main.querySelector("[data-export]");
  if (exp) exp.addEventListener("click", async () => {
    exp.disabled = true;
    try {
      const rows = await actions.export(keep(d), d.ctx);
      const csv = [COLS.join(","), ...rows.map((r) => COLS.map((c) => csvCell(r[c])).join(","))].join("\n");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      a.download = `audit-${d.ctx.org.id}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      showError(main, e, "Couldn't export the events.");
    }
    exp.disabled = false;
  });
}

export default { nav: "audit", default: "default", after, states: {
  "default": { render: (d) => log(d) + retention(d) },
  "filter-open": { render: (d) => log(d) + retention(d) },
  "filtered-agent": { render: log },
  "expanded": { render: log },
  "entity": { render: entity },
  "empty": { render: empty },
  "retention": { render: expired }
}};
