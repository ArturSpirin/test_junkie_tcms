/* Audit log: every write with its actor, on-behalf-of person, token and channel; filters, one expanded event, one entity's history, retention. */
import { I, ver, actor, dd, dr, toast, esc, lnk, person } from "../ui.js";

const who = (a) => a.kind === "system" ? `<span class="actor"><span class="av token">${I.cycle}</span><span>system</span><span class="kind">system</span></span>` : actor(a.kind, esc(a.id), { k: true });
const ent = (e) => `<span class="faint" style="font-size:12px">${esc(e.type)}</span> ${e.type === "case" || e.type === "cycle_case" ? `<a class="key" href="#entity">${esc(e.id)}</a>` : `<span class="${e.type === "token" ? "mono" : ""}">${esc(e.id)}</span>`}${e.version ? " " + ver(e.version, e.type === "cycle_case") : ""}`;
const forLine = (e) => (e.onBehalfOf ? `<div class="for">${I.person.replace(/16/g, "13")}<span>for ${esc(person(e.onBehalfOf)[0])}</span></div>` : "") + (e.token && e.actor.kind !== "token" ? `<div class="for">${I.key.replace(/16/g, "13")}<span class="mono">${esc(e.token)}</span></div>` : "");

/* filter option sets: the fixed kinds, actions, channels and object types; agents and people come from data */
const actorOptions = (d) => [{ group: "Kind" }, { v: "any", label: "Any actor", icon: I.filter }, { v: "person", label: "People", icon: I.person, hint: "signed-in members" }, { v: "agent", label: "Agents", icon: I.agent, hint: "non-human members" }, { v: "token", label: "Tokens", icon: I.key, hint: "a token with no agent" }, { v: "system", label: "System", icon: I.cycle, hint: "jobs, retention" },
  { group: "Agents" }, ...d.agents.map((a) => ({ v: `agent:${a.id}`, label: a.id, short: `${a.id} (agent)`, icon: I.agent, hint: `owner ${person(a.owner)[0].split(" ")[0]} · ${a.role}` })),
  { group: "People" }, ...d.members.map((m) => ({ v: m.handle, label: person(m.handle)[0], icon: I.person, hint: m.role }))];
const O_ACTION = [{ v: "any", label: "Any action", icon: I.filter }, { group: "Cases" }, { v: "cases.create", label: "cases.create" }, { v: "cases.update", label: "cases.update", hint: "new version" }, { v: "cases.restore", label: "cases.restore" }, { v: "cases.import", label: "cases.import" }, { v: "cases.move", label: "cases.move" },
  { group: "Cycles and results" }, { v: "cycles.bulk_create", label: "cycles.bulk_create" }, { v: "cycle_cases.refresh", label: "cycle_cases.refresh", hint: "pinned version moved" }, { v: "cycles.close", label: "cycles.close" }, { v: "results.create", label: "results.create" },
  { group: "Access" }, { v: "tokens.create", label: "tokens.create" }, { v: "tokens.revoke", label: "tokens.revoke", danger: true }, { v: "agents.create", label: "agents.create" }, { v: "agents.disable", label: "agents.disable", danger: true }];
const O_VIA = [{ v: "any", label: "Any channel", icon: I.filter }, "-", { v: "ui", label: "ui", icon: I.person, hint: "browser session (cookie + CSRF)" }, { v: "api", label: "api", icon: I.link, hint: "REST with a bearer token" }, { v: "mcp", label: "mcp", icon: I.mcp, hint: "MCP tool call, X-TCMS-Via: mcp" },
  { v: "reporter", label: "reporter", icon: I.upload, hint: "Test Junkie reporter from CI" }, { v: "consumer", label: "consumer", icon: I.external, hint: "consumer integration (§6)" }, { v: "system", label: "system", icon: I.cycle, hint: "jobs: refresh, retention" }];
const O_TYPE = [{ v: "any", label: "Any object", icon: I.filter }, "-", { v: "case", label: "case", icon: I.doc }, { v: "cycle_case", label: "cycle_case", icon: I.run }, { v: "cycle", label: "cycle", icon: I.cycle }, { v: "release", label: "release", icon: I.tag }, { v: "feature", label: "feature", icon: I.folder }, { v: "token", label: "token", icon: I.key }, { v: "agent", label: "agent", icon: I.agent }];

const day = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
const actorName = (v) => v.replace(/^\w+:/, "");
function filters(d) {
  const f = d.filter;
  const chips = [f.actor !== "any" ? `<span class="chip acc">actor: ${esc(actorName(f.actor))} <span class="x">${I.x}</span></span>` : "", f.entityId ? `<span class="chip acc">${esc(f.type)} ${esc(f.entityId)} <span class="x">${I.x}</span></span>` : ""].join("");
  const range = f.range.from ? Object.assign({}, f.range, { from: day(f.range.from), to: day(f.range.to || d.ctx.today) }) : f.range;
  return `<div class="afbar" role="search" aria-label="Filter events">
  <label class="in-ic">${I.search}<input class="in" placeholder="Search summary, entity id, request_id" aria-label="Search events"></label>
  ${dd({ value: f.actor, options: actorOptions(d), cls: "sm", pre: "Actor", search: "Find an actor…", name: "actor", label: "Actor" })}
  ${dd({ value: f.action, options: O_ACTION, cls: "sm", pre: "Action", search: "Find an action…", name: "action", label: "Action" })}
  ${dd({ value: f.via, options: O_VIA, cls: "sm", pre: "Via", name: "via", label: "Via", open: !!f.viaOpen, hl: f.viaOpen ? "mcp" : undefined })}
  ${dd({ value: f.type, options: O_TYPE, cls: "sm", pre: "Object", name: "type", label: "Object type" })}
  ${dr(range)}
  </div>
  <div class="afmeta">${chips}<span>${d.events.length} events</span><span class="mono">audit_list · GET /orgs/${esc(d.orgSlug)}/audit${esc(f.query)}</span></div>`;
}
const diffVal = (v, tag) => Array.isArray(v) ? esc(JSON.stringify(v)) : `<${tag}>${esc(v)}</${tag}>`;
/* a list change shows the old list as is and marks the added items in the new one */
const diffAfter = (c) => Array.isArray(c.after) ? `[${c.after.map((x) => (c.before.includes(x) ? esc(JSON.stringify(x)) : `<ins>${esc(JSON.stringify(x))}</ins>`)).join(", ")}]` : `<ins>${esc(c.after)}</ins>`;
function detail(e) {
  const x = e.detail || { changes: [] };
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
  <div class="acts"><a class="btn sm" href="${lnk("versions.html")}">${I.restore}Open ${esc(e.id)} history</a><a class="btn sm ghost" href="#entity">All events for ${esc(e.id)}</a><span class="sp"></span><button class="btn sm ghost" data-copy>${I.copy}Copy as JSON</button></div></div>`;
}
function table(list, open) {
  const go = (i) => (i === open ? "default" : "expanded");
  const row = (e, i) => `<tr class="ev${i === open ? " open" : ""}" data-go="${go(i)}" aria-expanded="${i === open}"><td class="when"><b>${esc(e.time.replace(" PT", ""))}</b><span>${esc(e.day)}</span></td><td>${who(e.actor)}${forLine(e)}</td><td><span class="act">${esc(e.action)}</span></td><td>${ent(e)}</td><td><span class="via">${esc(e.via)}</span></td><td class="hide-m muted" style="font-size:13px">${esc(e.summary)}</td><td style="width:36px"><span class="cv">${I.chev}</span></td></tr>` + (i === open ? `<tr class="xrow"><td colspan="7">${detail(e)}</td></tr>` : "");
  const mrow = (e, i) => `<div class="it${i === open ? " open" : ""}" data-go="${go(i)}"><div class="row"><span class="act">${esc(e.action)}</span><span class="via">${esc(e.via)}</span><span class="faint" style="font-size:12px;margin-left:auto">${esc(e.day.replace(/^\w+ /, ""))}, ${esc(e.time.replace(" PT", ""))}</span></div><div>${who(e.actor)}${forLine(e)}</div><div>${ent(e)}</div>${i === open ? detail(e) : ""}</div>`;
  return `<div class="card"><div class="tbl-wrap mswap cue"><table class="t atbl"><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Object</th><th>Via</th><th class="hide-m">Summary</th><th></th></tr></thead><tbody>${list.map(row).join("")}</tbody></table></div><div class="mlist">${list.map(mrow).join("")}</div></div>`;
}
const head = (d, h1 = "Audit log", crumbs = "") => `<div class="crumbs"><span>${esc(d.ctx.org.name)}</span><span class="sep">/</span>${crumbs || "<span>Audit log</span>"}</div>
<div class="ph"><div><div class="eyebrow">Append-only</div><h1>${h1}</h1></div><div class="actions"><button class="btn" data-export>${I.upload}Export CSV</button></div></div>
<p class="sub muted" style="margin-top:-10px;margin-bottom:20px">Every write, by a person, an agent or a token, with the person it acted for and the channel it came through. Kept ${d.retention.days} days; read needs <span class="mono">audit:read</span>.</p>`;
const retention = (d) => `<div class="banner info" style="margin-top:16px">${I.info}<div>Events older than ${d.retention.days} days (before ${esc(d.retention.oldest)}) are deleted nightly. Case versions and results are kept; only the audit trail expires. Export CSV to keep a copy.</div></div>`;
const log = (d) => head(d) + filters(d) + table(d.events, d.open);

const entity = (d) => {
  const n = d.entity;
  return head(d, esc(`${n.id} · ${n.title}`), `<a href="#default">Audit log</a><span class="sep">/</span><span>${esc(`${n.type} ${n.id}`)}</span>`) + filters(d) + table(d.events, d.open);
};
const empty = (d) => head(d) + filters(d) + `<div class="card"><div class="empty"><div class="ill">${I.audit}</div><h3>No events match</h3><p style="margin:0">${esc(actorName(d.filter.actor))} has done nothing today. Widen the period or clear a filter.</p><a class="btn" href="#default">Clear filters</a></div></div>`;
const expired = (d) => log(d) +
  `<div class="card" style="margin-top:16px"><div class="empty" style="padding:32px 16px"><div class="ill">${I.lock}</div><h3>Older events have expired</h3><p style="margin:0">Audit events are kept ${d.retention.days} days. The oldest kept is from ${esc(d.retention.oldest)}.</p></div></div>` + retention(d);

/* live: a row click opens or closes its event; buttons and a filter change give feedback. Wired once, on the document. */
let wired = false;
function wire() {
  if (wired) return;
  wired = true;
  document.addEventListener("click", (e) => {
    const t = e.target;
    if (!t.closest || !t.closest('[data-view="audit"]')) return;
    if (t.closest("[data-copy]")) { toast('<b>Copied.</b> <span class="muted">Event as JSON</span>'); return; }
    if (t.closest("[data-export]")) { toast('<b>Export started.</b> <span class="muted">CSV of the filtered events</span>'); return; }
    const g = t.closest("[data-go]");
    if (g && !t.closest("a, .xpanel")) location.hash = g.dataset.go;
  });
  document.addEventListener("dd:change", (e) => { if (e.target.closest && e.target.closest(".afbar")) toast(`<div><b>Filter applied.</b> <span class="muted">${esc(e.detail.name)}: ${esc(e.detail.value)}</span></div>`); });
  document.addEventListener("dr:change", (e) => toast(`<div><b>Range changed.</b> <span class="muted">${e.detail.value === "custom" ? "custom range" : esc(e.detail.value)}</span></div>`));
}

export default { nav: "audit", default: "default", after: () => wire(), states: {
  "default": { render: (d) => log(d) + retention(d) },
  "filter-open": { render: (d) => log(d) + retention(d) },
  "filtered-agent": { render: log },
  "expanded": { render: log },
  "entity": { render: entity },
  "empty": { render: empty },
  "retention": { render: expired }
}};
