/* Case version history: the immutable versions of one case, a compare of two, restore, and the cycles that pin them. */
import { I, st, ver, actor, modal, dd, lnk, esc, person } from "../ui.js";

const KIND_IC = { person: I.person, agent: I.agent, token: I.key };
const and = (xs) => (xs.length < 2 ? xs.join("") : xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1]);
/* inline Markdown code (`x`) in diff text */
const md = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
const seg = (s) => (s.del !== undefined ? `<del>${md(s.del)}</del>` : s.ins !== undefined ? `<ins>${md(s.ins)}</ins>` : md(s.text));

const vopts = (d) => [{ group: `${d.case.key} versions` }, ...d.versions.map((v) => ({
  v: String(v.n), short: "v" + v.n, label: `v${v.n} · ${v.note || "No change note"}`, icon: KIND_IC[v.kind],
  hint: `${person(v.who)[0]}${v.forWho ? " for " + person(v.forWho)[0] : ""} · ${v.via} · ${v.at}`
}))];

function vlist(d, a, b) {
  const current = d.versions[0].n;
  return `<div class="card vlist"><div class="hd"><div class="ttl"><span class="eyebrow">Immutable</span><span>Versions</span></div><span class="r faint" style="font-size:12px">${d.versions.length} versions</span></div>` + d.versions.map((v) => {
    const p = v.n === a ? "A" : v.n === b ? "B" : "";
    return `
  <div class="vi ${p ? "on" : ""}" role="button" tabindex="0" aria-pressed="${!!p}" aria-label="Pick v${v.n} to compare"><span class="pick${p ? " on" : ""}">${p}</span>
  <div style="min-width:0;flex:1"><div class="row">${ver(v.n)}${v.n === current ? '<span class="chip acc">current</span>' : ""}<span class="ell" style="font-size:13px">${v.note ? esc(v.note) : '<span class="faint">No change note</span>'}</span></div>
  <div class="meta">${actor(v.kind, esc(v.who), { k: false })}${v.forWho ? `<span>for ${esc(person(v.forWho)[0])}</span>` : ""}<span class="via">${esc(v.via)}</span><span>${esc(v.at)}</span></div></div></div>`;
  }).join("") + `</div>`;
}
function cbar(d, a, b, open) {
  return `<div class="card"><div class="bd roomy cbar">
    <div class="cf"><span class="eyebrow">From</span>${dd({ value: String(a), options: vopts(d), cls: "sm", w: "112px", open: open === "a", label: "Compare from version" })}</div>
    <span class="arrow">${I.chev}</span>
    <div class="cf"><span class="eyebrow">To</span>${dd({ value: String(b), options: vopts(d), cls: "sm", w: "112px", open: open === "b", label: "Compare to version" })}</div>
    <span class="sp"></span>
    <button class="btn sm" data-go="restore-confirm">${I.restore}Restore v${a}</button>
  </div></div>`;
}
function diff(d, a, b) {
  const x = d.diff;
  return `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Changes</span><span class="row">${ver(a)} ${I.chev} ${ver(b)}</span></div></div><div class="bd roomy diff">
  <div class="drow"><span class="f">Step order</span>${x.moves.map((m) => `<div class="moved">${esc(m.step)} “${esc(m.title)}” moved ${m.from} → ${m.to}</div>`).join("")}</div>
  ${x.fields.map((f) => `<div class="drow"><span class="f">${esc(f.label)}</span><div>${f.from.map(seg).join("")}</div><div>${f.to.map(seg).join("")}</div></div>`).join("\n  ")}
  <div class="drow"><span class="f">Change note</span><div class="muted">${esc(x.note.from)}</div><div>${esc(x.note.to)}</div></div>
  <div class="drow"><span class="f">Unchanged</span><div class="muted" style="grid-column:2/-1">${esc(x.unchanged)}</div></div>
  </div></div>`;
}
function used(d) {
  const name = (u) => (u.open ? `<a href="${lnk("cycles.html#detail")}">${esc(u.cycle)}</a>` : esc(u.cycle));
  return `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Pinned versions</span><span>Used in cycles</span></div><span class="r faint" style="font-size:12px">each cycle keeps the version pinned when the case was added</span></div>
  <div class="tbl-wrap mswap"><table class="t"><thead><tr><th>Cycle</th><th>Release</th><th>Pinned</th><th>Result</th><th></th></tr></thead><tbody>
  ${d.used.map((u) => `<tr class="${u.open ? "" : "dim"}"><td>${name(u)}</td><td>${u.release ? esc(u.release) : '<span class="faint">none</span>'}</td><td>${ver(u.pinned, 1)}</td><td>${st(u.result)}</td><td class="used-note">${esc(u.note)}</td></tr>`).join("")}
  </tbody></table></div>
  <div class="mlist">${d.used.map((u) => `<div class="it"><div class="row">${ver(u.pinned, 1)}${st(u.result)}<span class="used-note">${esc(u.note)}</span></div>${name(u)}<span class="faint" style="font-size:12px">Release ${esc(u.release || "none")}</span></div>`).join("")}</div></div>`;
}
const head = (d, tab) => {
  const c = d.case;
  return `<div class="crumbs"><a href="${lnk("tree.html")}">${esc(c.product)}</a><span class="sep">/</span><span>${esc(c.feature)}</span><span class="sep">/</span><a href="${lnk("case.html")}" class="key">${esc(c.key)}</a></div>
<div class="ph"><div class="ttl"><span class="eyebrow">Version history · ${esc(c.key)}</span><h1>${esc(c.title)}</h1></div><div class="actions"><a class="btn hide-n" href="${lnk("case.html")}">${I.chevl}Back to case</a></div></div>
<nav class="tabs" aria-label="History views"><a href="#default" class="${tab === "changes" ? "on" : ""}">${I.restore}Changes</a><a href="#used-in-cycles" class="${tab === "used" ? "on" : ""}">${I.cycle}Used in cycles</a></nav>`;
};
const page = (d, right, o = {}) => {
  const { a, b } = d.pick;
  return head(d, o.tab || "changes") + `<div class="split">${vlist(d, a, b)}<div class="stack">${right || cbar(d, a, b, o.open) + diff(d, a, b)}</div></div>`;
};

function compare(d) {
  const { a, b } = d.pick;
  return page(d, `<div class="banner info">${I.info}<div>Comparing two picked versions, <b>v${a}</b> and <b>v${b}</b> (<code>GET /cases/${esc(d.case.key)}/versions?compare=${a},${b}</code>). Pick any two in the list or in From and To.</div></div>` + cbar(d, a, b, "a") + diff(d, a, b));
}
function restoreConfirm(d) {
  const a = d.pick.a, next = d.versions[0].n + 1;
  const kept = d.versions.filter((v) => v.n > a).map((v) => "v" + v.n).reverse();
  const pinned = [...new Set(d.used.filter((u) => u.open).map((u) => u.pinned))].sort((x, y) => x - y).map((n) => "v" + n);
  return page(d) + modal(`Restore v${a} as v${next}?`, `<p style="margin-top:0">Restoring copies v${a} into a <b>new version v${next}</b>. ${and(kept)} stay in history; nothing is deleted.</p>
    <div class="field"><label for="cn">Change note</label><input id="cn" class="in" value="${esc(d.draft.note)}"></div>
    <div class="banner warn mb0">${I.info}<div>Open cycles keep their pinned versions (${pinned.join(", ")}). Use “Refresh to v${next}” in a cycle to move an untested case.</div></div>`,
    `<span class="l mono">POST /cases/${esc(d.case.key)}/versions/${a}:restore</span><button class="btn" data-back>Cancel</button><button class="btn primary">Restore as v${next}</button>`);
}
function restored(d) {
  const { a, b } = d.pick, prev = d.versions[1].n;
  return page(d, `<div class="card"><div class="hd"><div class="ttl"><span class="eyebrow">Restored</span><span class="row wrap">${ver(a)} and ${ver(b)} are identical</span></div><span class="r chip acc">current: v${b}</span></div><div class="bd roomy muted">v${b} is a copy of v${a} with its own change note. Compare v${prev} → v${b} to see what the restore undid.</div></div>` + cbar(d, a, b)) +
    `<div class="toast" role="status"><div><b>v${a} restored as v${b}.</b> <span class="muted">Audit: cases.restore by ${esc(person(d.ctx.user.handle)[0])}.</span></div></div>`;
}

/* the Restore button moves to the confirm state; one document listener, added once */
let wired = false;
const wire = () => {
  if (wired) return;
  wired = true;
  document.addEventListener("click", (e) => { const go = e.target.closest("[data-go]"); if (go) location.hash = go.dataset.go; });
};

export default { nav: "cases", default: "default", states: {
  "default": { render: (d) => page(d) },
  "compare": { render: compare },
  "restore-confirm": { render: restoreConfirm },
  "restored": { render: restored },
  "used-in-cycles": { render: (d) => page(d, used(d), { tab: "used" }) }
}, after: () => wire() };
