/* Consumers: the paired machines list, the pairing flow and one machine's detail. */
import { I, crumbs, lnk, modal, dd, tg, tipA, pinTip, psearch, hl, esc } from "../ui.js";

const mst = (s) => `<span class="mst ${s}">${s}</span>`;
const prods = (p) => p.map((x) => `<span class="chip mono">${esc(x)}</span>`).join(" ");
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const pairBtn = `<a class="btn primary" href="#pair">${I.plus}Pair a machine</a>`;
const listHead = () => head("Machines", "Consumers", crumbs([["Consumers"], ["Machines"]]), pairBtn);
const FILTERS = ["all", "online", "busy", "offline"];

function list(d, banner = "") {
  const q = d.q, f = d.filter, all = d.machines;
  let ms = all;
  if (f !== "all") ms = ms.filter((m) => m.status === f);
  if (q) ms = ms.filter((m) => m.name.toLowerCase().includes(q.toLowerCase()));
  const card = (m) => `<a class="card mcard${m.status === "offline" ? " off" : ""}" href="#detail"><div class="mh2"><span class="pi">${I.server}</span><h3>${hl(esc(m.name), q)}</h3>${mst(m.status)}</div>
    <div class="meta"><div><span>Heartbeat</span><b>${esc(m.heartbeat)}</b></div><div><span>Jobs today</span><b>${m.jobsToday}</b></div><div><span>System</span><b>${esc(m.os)}</b></div><div><span>Test Junkie</span><b class="mono">${esc(m.tj)} · py ${esc(m.python)}</b></div></div>
    <div class="ft">${prods(m.products)}<span class="sp"></span>${m.projects} project${m.projects > 1 ? "s" : ""}</div></a>`;
  const seg = FILTERS.map((s) => `<button class="${s === f ? "on" : ""}" aria-pressed="${s === f}" data-hash="${s === "all" ? "list" : "filter-" + s}">${s === "all" ? "All" : s[0].toUpperCase() + s.slice(1)} <span class="faint">${s === "all" ? all.length : all.filter((m) => m.status === s).length}</span></button>`).join("");
  const body = ms.length ? `<div class="g3 ms">${ms.map(card).join("")}</div>` : `<div class="card"><div class="empty"><div class="ill">${I.search}</div><h3>No machines match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:420px">Search looks at the names people gave their machines when they paired them.</p><a class="btn" href="#list">Clear search</a></div></div>`;
  return listHead() + banner + `<div class="sub" style="margin-bottom:16px">Machines running Test Junkie that pull automated jobs from TCMS. Each one shows the name it was given when it was paired.</div>` +
    `<div class="tools">${psearch({ q, ph: "Search machines by name", cnt: ms.length + (ms.length === 1 ? " machine" : " machines"), clear: "#list" })}<div class="seg" role="group" aria-label="Status">${seg}</div></div>` +
    `<div class="sec-h"><h2>Paired machines</h2><span class="r faint" style="font-size:12px">${all.filter((m) => m.status !== "offline").length} of ${all.length} online</span></div>` + body;
}
/* the status filter buttons move to their state */
const segNav = (main) => main.querySelectorAll(".seg [data-hash]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.hash; }));

/* pairing: RFC 8628 device flow; the person approving names the machine */
const steps = (cur) => `<ol class="steps">${["Run the command", "Enter the code", "Name and approve"].map((s, i) => `<li class="${i < cur ? "done" : i === cur ? "on" : ""}"><span class="no">${i < cur ? "✓" : i + 1}</span><span class="lb">${s}</span></li>`).join("")}</ol>`;
const pairHead = () => head("Pair a machine", "Consumers · Machines", crumbs([["Consumers"], ["Machines", "consumers.html"], ["Pair a machine"]]));
const pairCode = (d) => {
  const p = d.pair;
  const ch = Array.from({ length: p.codeLength }, (_, i) => `<span>${esc(p.typed[i] || "")}</span>`);
  const half = p.codeLength / 2;
  return pairHead() + `<div class="pairw">${steps(1)}<div class="card"><div class="hd"><h2>Enter the code from the machine</h2></div><div class="bd">
  <p class="muted">On the machine, run the command below. It prints an ${p.codeLength}-character code that works for ${p.ttlMin} minutes.</p>
  <div class="cmd">${I.code}<span>tj tcms pair ${esc(p.server)}</span><button class="icon-btn" aria-label="Copy">${I.copy}</button></div>
  <div class="field" style="margin-top:20px"><label>Pairing code</label><div class="code-in" aria-label="Pairing code">${ch.slice(0, half).join("")}<span class="dash">–</span>${ch.slice(half).join("")}</div></div>
  </div><div class="foot-bar"><span class="l mono">POST /pair {"user_code":"${esc(p.typed.slice(0, half) + "-" + p.typed.slice(half))}…"}</span><a class="btn" href="#list">Cancel</a><a class="btn primary" href="#pair-approve">Continue</a></div></div></div>`;
};
const pairName = (d) => {
  const p = d.pair;
  const none = p.name === "";
  const opts = [{ group: "Products" }, ...d.ctx.products.map((x) => ({ v: x.key, label: `${x.key} · ${x.name}`, icon: `<span class="mark xs${x.markCls ? " " + x.markCls : ""}">${esc(x.key[0])}</span>` }))];
  return pairHead() + `<div class="pairw">${steps(2)}<div class="card"><div class="hd"><h2>Name this machine and approve it</h2><span class="r faint" style="font-size:12px">code expires in ${esc(p.expiresIn)}</span></div><div class="bd">
  <div class="field"><label for="mn">Machine name</label><input id="mn" class="in" value="${esc(p.name)}" placeholder="For example, QA lab Mac mini"${none ? ' aria-invalid="true"' : ""}>
    <small class="${none ? "err" : "faint"}">${none ? "Give the machine a name." : "This is the only name anyone sees for it, in lists, runs and the audit log."}</small></div>
  <dl class="kv" style="margin:6px 0 18px"><dt>System</dt><dd>${esc(p.os)}</dd><dt>Test Junkie</dt><dd class="mono">${esc(p.tj)} · Python ${esc(p.python)}</dd><dt>Projects found</dt><dd>${p.projects.length} (${esc(p.projects.join(", "))})</dd></dl>
  <div class="field"><label>Products it may run</label>${dd({ multi: true, value: p.products, options: opts, w: "100%", label: "Products" })}</div>
  ${tg(p.acceptNow, "Accept jobs right away", "Off: the machine pairs but stays paused until you resume it")}
  </div><div class="foot-bar"><span class="l mono">POST /pair/approve {"name":"${esc(p.sentName)}"}</span><a class="btn" href="#pair">Back</a><a class="btn danger" href="#list">Deny</a><a class="btn primary" href="#paired">Approve machine</a></div></div></div>`;
};
const pairedBanner = (d) => `<div class="banner info">${I.check}<div style="flex:1"><b>${esc(d.paired.name)} is paired.</b> It may run ${esc(d.paired.products.join(", "))} jobs. Its token went to the machine only; nobody sees it here.</div><span class="r"><a class="btn sm" href="#detail">Open machine</a></span></div>`;

/* heartbeat: polls per hour against the expected count, with missed polls */
function hbChart(hb) {
  const B = hb.beats, n = B.length, full = hb.expected;
  const HL = B.map((_, i) => `${String((i + hb.startHour) % 24).padStart(2, "0")}:00`);
  return `<div class="chart hb" role="img" aria-label="Heartbeats per hour, last 24 hours">${[50].map((p) => `<span class="gl" style="bottom:${p}%"></span>`).join("")}${B.map((h, i) => {
    const miss = i === n - 1 ? 0 : full - h;
    return `<div class="col${i === n - 1 ? " now" : ""}"${tipA(`Today ${HL[i]}–${HL[(i + 1) % 24].slice(0, 2)}:00 ${hb.tz}`, [["Heartbeats", "var(--accent)", h], ["Missed", "var(--st-error)", miss], ["Jobs run", "var(--retest)", hb.jobs[i]]], ["Status", h === 0 ? "offline" : miss > 10 ? "gaps" : "online"])}>${h ? `<i class="a" style="height:${(h / full) * 100}%"></i>` : ""}${miss && h ? `<i class="c" style="height:${(miss / full) * 100}%"></i>` : ""}${!h ? `<i class="c" style="height:6%"></i>` : ""}</div>`;
  }).join("")}</div><div class="chart-x">${HL.map((l, i) => `<span>${i % 4 === 0 ? l : ""}</span>`).join("")}</div>`;
}
const jobRow = (j, s) => {
  if (j.state === "rejected") return `<div class="job"><b>${I.warn}<span class="ell">${esc(j.name)}</span></b><span class="pill cancel">rejected</span><small>project <span class="mono">${esc(j.project)}</span> is not registered on this machine</small></div>`;
  if (j.state === "queued") return `<div class="job"><b>${I.clock}<span class="ell">${esc(j.name)}</span></b><span class="chip">queued</span><small>${esc(j.project)} · ${esc(j.detail)}</small></div>`;
  return `<div class="job"><b>${I.run}<span class="ell">${esc(j.name)}</span></b>${s === "offline" ? '<span class="chip">waiting</span>' : mst("busy")}<small>${esc(j.project)} · ${esc(j.detail)} · ${j.done} of ${j.total} done</small><div class="prog"><i style="width:${(j.done / j.total) * 100}%"></i></div></div>`;
};
function detail(d, banner = "") {
  const m = d.machine, s = m.status, name = esc(m.name);
  const open = m.jobs.filter((j) => j.state !== "rejected").length;
  return head(name, "Machine · Consumers", crumbs([["Consumers"], ["Machines", "consumers.html"], [name]]),
    `<a class="btn" href="#rename">${I.edit}Rename</a><a class="btn hide-n" href="#detail">${I.clock}Pause jobs</a><a class="btn danger" href="#revoke-confirm">${I.trash}Revoke</a>`) + banner +
  `<div class="kpis">
    <div class="kpi"><span class="l">Status</span><span class="v">${mst(s)}</span><span class="d">${s === "offline" ? `no heartbeat for ${esc(m.silentFor)}` : `heartbeat ${esc(m.heartbeat)}`}</span></div>
    <div class="kpi"><span class="l">Jobs today</span><span class="v">${m.jobsToday}</span><span class="d">${m.rejectedToday} rejected</span></div>
    <div class="kpi"><span class="l">Tests found</span><span class="v">${m.testsFound}</span><span class="d">${m.testsLinked} linked to cases</span></div>
    <div class="kpi"><span class="l">Test Junkie</span><span class="v mono" style="font-size:20px">${esc(m.tj)}</span><span class="d">Python ${esc(m.python)} · ${esc(m.os)}</span></div>
  </div>
  <div class="g2" style="margin-bottom:20px">
    <div class="card"><div class="hd"><h2>Job queue</h2><span class="r faint" style="font-size:12px">${open} job${open === 1 ? "" : "s"}</span></div>
      ${m.jobs.map((j) => jobRow(j, s)).join("\n      ")}
    </div>
    <div class="card"><div class="hd"><h2>Projects and products</h2></div><div class="bd">
      <div class="fx-r">${m.projects.map((p) => `<span class="fx col">${I.folder}<b>${esc(p.name)}</b><span class="r">${prods(p.products)}</span></span>`).join("")}</div>
      <p class="faint" style="font-size:12px;margin:12px 0 0">Projects are registered on the machine with <span class="mono">tj tcms project add</span>. It may run jobs for ${esc(m.products.join(", "))} only.</p></div></div>
  </div>
  <div class="card" style="margin-bottom:20px"><div class="hd"><h2>Heartbeat, last 24 hours</h2><span class="r legend"><span style="--c:var(--accent)">heartbeats</span><span style="--c:var(--st-error)">missed</span></span></div><div class="bd">${hbChart(m.hb)}</div></div>
  <div class="card"><div class="hd"><h2>Tests on this machine</h2><span class="r faint" style="font-size:12px">rescanned ${esc(m.rescanned)}</span></div>
    <div class="tbl-wrap"><table class="t"><thead><tr><th>Test</th><th>Case</th></tr></thead><tbody>${m.tests.map((t) => `<tr><td><code title="${esc(t.ref)}">${esc(t.ref)}</code></td><td>${t.caseKey ? `<a class="fx" href="${lnk("case.html")}">${I.doc}<b>${esc(t.caseKey)}</b></a>` : `<span class="chip">no case yet</span>`}</td></tr>`).join("")}</tbody></table></div>
    <div class="foot-bar"><span class="l">Linked through each case's <span class="mono">automation_ref</span> · ${m.tests.length} of ${m.testsFound} shown</span><button class="btn sm">Show all</button></div></div>`;
}

const empty = () => listHead() + `<div class="card"><div class="hd"><h2>Paired machines</h2></div><div class="empty"><div class="ill">${I.server}</div><h3>No machines paired</h3><p class="muted" style="margin:0 auto 14px;max-width:460px">Run <span class="mono">tj tcms pair</span> on a machine with Test Junkie, enter its code here, and give it a name. Paired machines pull automated jobs for the products you allow.</p><a class="btn primary" href="#pair">${I.plus}Pair a machine</a></div></div>`;

export default { nav: "consumers", default: "list", states: {
  "list": { render: list, after: segNav },
  "filter-online": { render: list, after: segNav },
  "filter-busy": { render: list, after: segNav },
  "filter-offline": { render: list, after: segNav },
  "search": { render: list, after: segNav },
  "search-empty": { render: list, after: segNav },
  "pair": { render: pairCode },
  "pair-approve": { render: pairName },
  "pair-noname": { render: pairName },
  "paired": { render: (d) => list(d, pairedBanner(d)), after: segNav },
  "detail": { render: (d) => detail(d) },
  "detail-hover": { render: (d) => detail(d), after: (m, d) => pinTip(m.querySelectorAll(".chart .col")[d.hoverCol]) },
  "rename": { render: (d) => detail(d) + modal("Rename machine", `<div class="field"><label for="rn">Machine name</label><input id="rn" class="in" value="${esc(d.renameTo)}" autofocus><small class="faint">Past runs and the audit log show the new name.</small></div>`, `<span class="l mono">PATCH /consumers/${esc(d.machine.id)} {"name":…}</span><a class="btn" href="#detail">Cancel</a><a class="btn primary" href="#detail">Save name</a>`) },
  "job-rejected": { render: (d) => detail(d, `<div class="banner err">${I.warn}<div><b>Job rejected by ${esc(d.machine.name)}.</b> <span class="mono">${esc(d.machine.rejectError)}</span></div></div>`) },
  "offline": { render: (d) => { const open = d.machine.jobs.filter((j) => j.state !== "rejected").length; return detail(d, `<div class="banner warn">${I.warn}<div><b>${esc(d.machine.name)} is offline.</b> No heartbeat since ${esc(d.machine.lastHeartbeat)}. Its ${open} jobs wait; move them to another machine or wait for it to come back.</div><span class="r"><a class="btn sm" href="${lnk("start.html#offline-mid")}">Move jobs</a></span></div>`); } },
  "empty": { render: empty },
  "revoke-confirm": { render: (d) => detail(d) + modal(`Revoke ${esc(d.machine.name)}?`, `<p style="margin-top:0">Its token stops working at once. The running job is cancelled and its queued job goes back to the cycle. Past results stay.</p>`, `<span class="l mono">DELETE /consumers/${esc(d.machine.id)}</span><a class="btn" href="#detail">Cancel</a><a class="btn danger" href="#list">Revoke machine</a>`) }
}};
