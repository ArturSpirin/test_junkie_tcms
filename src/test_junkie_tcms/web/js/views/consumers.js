/* Consumers: the paired machines list, the pairing flow and one machine's detail.
   The data and the writes are data/consumers.js. */
import { I, crumbs, modal, footBar, dd, tg, tipA, pinTip, psearch, hl, esc } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/consumers.js";

const mst = (s) => `<span class="mst ${s}">${s}</span>`;
const paused = (m) => (m.paused ? ' <span class="chip">paused</span>' : "");
const prods = (p) => p.map((x) => `<span class="chip mono">${esc(x)}</span>`).join(" ");
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const pairBtn = `<a class="btn primary" href="#pair">${I.plus}Pair a machine</a>`;
const listHead = () => head("Machines", "Consumers", crumbs([["Consumers"], ["Machines"]]), pairBtn);
const machinesHref = () => href("consumers");
const FILTERS = ["all", "online", "busy", "offline"];

/* d.machines is what the server matched for d.q and d.filter (consumers_list?q=&status=); d.counts counts each status */
function list(d, banner = "") {
  const q = d.q, f = d.filter, ms = d.machines, n = d.counts;
  const card = (m) => `<a class="card mcard${m.status === "offline" ? " off" : ""}" href="${href("consumers", { id: m.id })}"><div class="mh2"><span class="pi">${I.server}</span><h3>${hl(esc(m.name), q)}</h3>${mst(m.status)}${paused(m)}</div>
    <div class="meta"><div><span>Heartbeat</span><b>${esc(m.heartbeat)}</b></div><div><span>System</span><b>${esc(m.os)}</b></div><div><span>Test Junkie</span><b class="mono">${esc(m.tj)} · py ${esc(m.python)}</b></div></div>
    <div class="ft">${prods(m.products)}<span class="sp"></span>${m.projects} project${m.projects === 1 ? "" : "s"}</div></a>`;
  const seg = FILTERS.map((s) => `<button class="${s === f ? "on" : ""}" aria-pressed="${s === f}" data-href="${esc(href("consumers", { status: s === "all" ? null : s, q: q || null }))}">${s === "all" ? "All" : s[0].toUpperCase() + s.slice(1)} <span class="faint">${n[s]}</span></button>`).join("");
  const body = ms.length ? `<div class="g3 ms">${ms.map(card).join("")}</div>` : `<div class="card"><div class="empty"><div class="ill">${I.search}</div><h3>No machines match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:420px">Search looks at the names people gave their machines when they paired them.</p><a class="btn" href="${href("consumers", { status: f === "all" ? null : f })}">Clear search</a></div></div>`;
  return listHead() + banner + `<div class="sub" style="margin-bottom:16px">Machines running Test Junkie that pull automated jobs from TCMS. Each one shows the name it was given when it was paired.</div>` +
    `<div class="tools">${psearch({ q, ph: "Search machines by name", cnt: ms.length + (ms.length === 1 ? " machine" : " machines"), clear: href("consumers", { status: f === "all" ? null : f }) })}<div class="seg" role="group" aria-label="Status">${seg}</div></div>` +
    `<div class="sec-h"><h2>Paired machines</h2><span class="r faint" style="font-size:12px">${n.online + n.busy} of ${n.all} online</span></div>` + body;
}

/* pairing: RFC 8628 device flow; the person approving names the machine */
const steps = (cur) => `<ol class="steps">${["Run the command", "Enter the code", "Name and approve"].map((s, i) => `<li class="${i < cur ? "done" : i === cur ? "on" : ""}"><span class="no">${i < cur ? "✓" : i + 1}</span><span class="lb">${s}</span></li>`).join("")}</ol>`;
const pairHead = () => head("Pair a machine", "Consumers · Machines", crumbs([["Consumers"], ["Machines", machinesHref()], ["Pair a machine"]]));
const codeCells = (p) => {
  const ch = Array.from({ length: p.codeLength }, (_, i) => `<span>${esc(p.typed[i] || "")}</span>`);
  const half = p.codeLength / 2;
  return `${ch.slice(0, half).join("")}<span class="dash">–</span>${ch.slice(half).join("")}`;
};
const pairCode = (d) => {
  const p = d.pair;
  const ttl = p.ttlMin ? ` that works for ${p.ttlMin} minutes` : "";
  return pairHead() + `<div class="pairw">${steps(1)}<div class="card"><div class="hd"><h2>Enter the code from the machine</h2></div><div class="bd">
  <p class="muted">On the machine, run the command below. It prints an ${p.codeLength}-character code${ttl}.</p>
  <div class="cmd">${I.code}<span>tj tcms pair ${esc(p.server)}</span><button class="icon-btn" aria-label="Copy" data-act="copy">${I.copy}</button></div>
  <div class="field" style="margin-top:20px"><label>Pairing code</label><div class="code-in" aria-label="Pairing code" tabindex="0">${codeCells(p)}</div></div>
  </div>${footBar(`<a class="btn" href="${machinesHref()}">Cancel</a><a class="btn primary" data-act="continue" href="${href("consumers", { code: p.typed || null })}">Continue</a>`)}</div></div>`;
};
const pairName = (d, none = false) => {
  const p = d.pair;
  const opts = [{ group: "Products" }, ...d.ctx.products.map((x) => ({ v: x.key, label: `${x.key} · ${x.name}`, icon: `<span class="mark xs${x.markCls ? " " + x.markCls : ""}">${esc(x.key[0])}</span>` }))];
  return pairHead() + `<div class="pairw">${steps(2)}<div class="card"><div class="hd"><h2>Name this machine and approve it</h2><span class="r faint" style="font-size:12px">code expires in ${esc(p.expiresIn)}</span></div><div class="bd">
  <div class="field"><label for="mn">Machine name</label><input id="mn" class="in" value="${esc(p.name)}" placeholder="For example, QA lab Mac mini"${none ? ' aria-invalid="true"' : ""}>
    <small class="${none ? "err" : "faint"}">${none ? "Give the machine a name." : "This is the only name anyone sees for it, in lists, runs and the audit log."}</small></div>
  <dl class="kv" style="margin:6px 0 18px"><dt>System</dt><dd>${esc(p.os)}</dd><dt>Test Junkie</dt><dd class="mono">${esc(p.tj)} · Python ${esc(p.python)}</dd><dt>Projects found</dt><dd>${p.projects.length} (${esc(p.projects.join(", "))})</dd></dl>
  <div class="field"><label>Products it may run</label>${dd({ multi: true, value: p.products, options: opts, w: "100%", label: "Products", name: "products" })}</div>
  ${tg(p.acceptNow, "Accept jobs right away", "Off: the machine pairs but stays paused until you resume it", { name: "accept" })}
  </div>${footBar(`<a class="btn" href="${href("consumers", { code: p.code || null }, "pair")}">Back</a><button class="btn danger" data-act="deny">Deny</button><button class="btn primary" data-act="approve">Approve machine</button>`)}</div></div>`;
};
const pairedBanner = (d) => `<div class="banner info">${I.check}<div style="flex:1"><b>${esc(d.paired.name)} is paired.</b> It may run ${esc(d.paired.products.join(", "))} jobs. Its token went to the machine only; nobody sees it here.</div><span class="r"><a class="btn sm" href="${href("consumers", { id: d.paired.id })}">Open machine</a></span></div>`;

/* heartbeat: polls per hour, with missed polls when the expected count is known */
function hbChart(hb) {
  const B = hb.beats, n = B.length, full = hb.expected || Math.max(1, ...B);
  const HL = B.map((_, i) => `${String((i + hb.startHour) % 24).padStart(2, "0")}:00`);
  return `<div class="chart hb" role="img" aria-label="Heartbeats per hour, last 24 hours">${[50].map((p) => `<span class="gl" style="bottom:${p}%"></span>`).join("")}${B.map((h, i) => {
    const miss = i === n - 1 || !hb.expected ? 0 : full - h;
    return `<div class="col${i === n - 1 ? " now" : ""}"${tipA(`${HL[i]}–${HL[(i + 1) % 24].slice(0, 2)}:00 ${hb.tz}`, [["Heartbeats", "var(--accent)", h], ...(hb.expected ? [["Missed", "var(--st-error)", miss]] : []), ["Jobs run", "var(--retest)", hb.jobs[i]]], ["Status", h === 0 ? "offline" : miss > 10 ? "gaps" : "online"])}>${h ? `<i class="a" style="height:${(h / full) * 100}%"></i>` : ""}${miss && h ? `<i class="c" style="height:${(miss / full) * 100}%"></i>` : ""}${!h ? `<i class="c" style="height:6%"></i>` : ""}</div>`;
  }).join("")}</div><div class="chart-x">${HL.map((l, i) => `<span>${i % 4 === 0 ? l : ""}</span>`).join("")}</div>`;
}
const jobRow = (j, s) => {
  if (j.state === "rejected") return `<div class="job"><b>${I.warn}<span class="ell">${esc(j.name)}</span></b><span class="pill cancel">rejected</span><small>project <span class="mono">${esc(j.project)}</span> · ${esc(j.reason)}</small></div>`;
  if (j.state === "queued") return `<div class="job"><b>${I.clock}<span class="ell">${esc(j.name)}</span></b><span class="chip">queued</span><small>${esc(j.project)} · ${esc(j.detail)}</small></div>`;
  const progress = j.done === null || j.done === undefined ? "" : ` · ${j.done} of ${j.total} done`;
  return `<div class="job"><b>${I.run}<span class="ell">${esc(j.name)}</span></b>${s === "offline" ? '<span class="chip">waiting</span>' : mst("busy")}<small>${esc(j.project)} · ${esc(j.detail)}${progress}</small>${progress ? `<div class="prog"><i style="width:${(j.done / j.total) * 100}%"></i></div>` : ""}</div>`;
};
function detail(d, banner = "") {
  const m = d.machine, s = m.status, name = esc(m.name);
  const open = m.jobs.filter((j) => j.state !== "rejected").length;
  return head(name, "Machine · Consumers", crumbs([["Consumers"], ["Machines", machinesHref()], [name]]),
    `<a class="btn" href="#rename">${I.edit}Rename</a><button class="btn hide-n" data-act="${m.paused ? "resume" : "pause"}">${I.clock}${m.paused ? "Resume jobs" : "Pause jobs"}</button><a class="btn danger" href="#revoke-confirm">${I.trash}Revoke</a>`) + banner +
  `<div class="kpis">
    <div class="kpi"><span class="l">Status</span><span class="v">${mst(s)}${paused(m)}</span><span class="d">${s === "offline" ? (m.silentFor ? `no heartbeat for ${esc(m.silentFor)}` : "no heartbeat yet") : `heartbeat ${esc(m.heartbeat)}`}</span></div>
    <div class="kpi"><span class="l">Jobs, last 24 h</span><span class="v">${m.jobsToday}</span><span class="d">${m.rejectedToday} rejected</span></div>
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
  <div class="card" style="margin-bottom:20px"><div class="hd"><h2>Heartbeat, last 24 hours</h2><span class="r legend"><span style="--c:var(--accent)">heartbeats</span>${m.hb.expected ? '<span style="--c:var(--st-error)">missed</span>' : ""}</span></div><div class="bd">${hbChart(m.hb)}</div></div>
  <div class="card"><div class="hd"><h2>Tests on this machine</h2><span class="r faint" style="font-size:12px">rescanned ${esc(m.rescanned)}</span></div>
    <div class="tbl-wrap"><table class="t"><thead><tr><th>Test</th><th>Case</th></tr></thead><tbody>${m.tests.map((t) => `<tr><td><code title="${esc(t.ref)}">${esc(t.ref)}</code></td><td>${t.caseKey ? `<a class="fx" href="${href("case", { id: t.caseKey })}">${I.doc}<b>${esc(t.caseKey)}</b></a>` : `<span class="chip">no case yet</span>`}</td></tr>`).join("")}</tbody></table></div>
    ${footBar(m.allTests ? "" : `<button class="btn sm" data-act="all-tests">Show all</button>`, `Linked to cases by their automation ref · ${m.tests.length} of ${m.testsFound} shown`)}</div>`;
}
const moveHref = (m) => {
  const j = m.jobs.find((x) => x.state !== "rejected");
  return j ? href("start", { id: j.cycleId }) : href("cycles");
};
const offline = (d) => {
  const m = d.machine;
  const open = m.jobs.filter((j) => j.state !== "rejected").length;
  return detail(d, `<div class="banner warn">${I.warn}<div><b>${esc(m.name)} is offline.</b> ${m.lastHeartbeat ? `No heartbeat since ${esc(m.lastHeartbeat)}.` : "No heartbeat yet."} Its ${open} jobs wait; move them to another machine or wait for it to come back.</div><span class="r"><a class="btn sm" href="${moveHref(m)}">Move jobs</a></span></div>`);
};

const empty = () => listHead() + `<div class="card"><div class="hd"><h2>Paired machines</h2></div><div class="empty"><div class="ill">${I.server}</div><h3>No machines paired</h3><p class="muted" style="margin:0 auto 14px;max-width:460px">Run <span class="mono">tj tcms pair</span> on a machine with Test Junkie, enter its code here, and give it a name. Paired machines pull automated jobs for the products you allow.</p><a class="btn primary" href="#pair">${I.plus}Pair a machine</a></div></div>`;

/* the real controls: search (Enter) and the status filter ask the server; the pairing code, approve and deny;
   rename, pause or resume, revoke and show all tests on a machine */
const picks = (main, name) => [...main.querySelectorAll(`[data-name="${name}"] .dd-o.sel`)].map((o) => o.dataset.v);
function click(main, act, run, where, label) {
  const btn = main.querySelector(`[data-act=${act}]`);
  if (!btn) return;
  btn.addEventListener("click", async (e) => {
    e.preventDefault();
    btn.disabled = true;
    try {
      await run();
    } catch (err) {
      showError(where(), err, label);
      btn.disabled = false;
    }
  });
}
function after(main, state, d) {
  const box = main.querySelector(".psearch input");
  if (box) box.addEventListener("keydown", (e) => {
    if (e.key === "Enter") location.assign(href("consumers", { q: box.value.trim() || null, status: d.filter === "all" ? null : d.filter }));
  });
  main.querySelectorAll(".seg [data-href]").forEach((b) => b.addEventListener("click", () => location.assign(b.dataset.href)));
  const p = d.pair;
  const code = main.querySelector(".code-in");
  if (code && p) {
    let typed = p.typed;
    const go = main.querySelector("[data-act=continue]");
    const show = () => { code.innerHTML = codeCells({ ...p, typed }); go.href = href("consumers", { code: typed || null }); };
    const take = (s) => { typed = (typed + s.replace(/[^a-z0-9]/gi, "").toUpperCase()).slice(0, p.codeLength); show(); };
    code.addEventListener("keydown", (e) => {
      if (e.key === "Backspace") { typed = typed.slice(0, -1); show(); e.preventDefault(); }
      else if (e.key === "Enter") location.assign(go.href);
      else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) { take(e.key); e.preventDefault(); }
    });
    code.addEventListener("paste", (e) => { take(e.clipboardData.getData("text")); e.preventDefault(); });
    code.focus();
  }
  const copy = main.querySelector("[data-act=copy]");
  if (copy) copy.addEventListener("click", () => navigator.clipboard.writeText(copy.previousElementSibling.textContent));
  const card = () => main.querySelector(".pairw .card .bd") || main;
  const at = () => main.querySelector(".modal .mb") || main;
  if (p && p.code) {
    click(main, "approve", async () => {
      const name = main.querySelector("#mn").value.trim();
      if (!name) { location.replace("#pair-noname"); return; }
      const c = await actions.approve({ code: p.code, name, products: picks(main, "products"), acceptNow: main.querySelector("input[name=accept]").checked }, d.ctx);
      location.assign(href("consumers", { paired: c.id }));
    }, card, "Couldn't approve the machine.");
    click(main, "deny", async () => {
      await actions.deny(p.code, d.ctx);
      location.assign(machinesHref());
    }, card, "Couldn't deny the pairing request.");
  }
  const m = d.machine;
  if (!m || !main.querySelector(".kpis")) return;
  const reload = () => location.assign(href("consumers", { id: m.id }));
  click(main, "rename", async () => { await actions.rename(m.id, main.querySelector("#rn").value.trim(), d.ctx); reload(); }, at, "Couldn't rename the machine.");
  click(main, "pause", async () => { await actions.pause(m.id, d.ctx); reload(); }, at, "Couldn't pause the machine.");
  click(main, "resume", async () => { await actions.resume(m.id, d.ctx); reload(); }, at, "Couldn't resume the machine.");
  click(main, "revoke", async () => { await actions.revoke(m.id, d.ctx); location.assign(machinesHref()); }, at, "Couldn't revoke the machine.");
  click(main, "all-tests", async () => location.assign(href("consumers", { id: m.id, tests: "all" })), at, "Couldn't load the tests.");
}

export default { nav: "consumers", default: "list", after, states: {
  "list": { render: list },
  "filter-online": { render: list },
  "filter-busy": { render: list },
  "filter-offline": { render: list },
  "search": { render: list },
  "search-empty": { render: list },
  "pair": { render: pairCode },
  "pair-approve": { render: (d) => pairName(d) },
  "pair-noname": { render: (d) => pairName(d, true) },
  "paired": { render: (d) => list(d, pairedBanner(d)) },
  "detail": { render: (d) => detail(d) },
  "detail-hover": { render: (d) => detail(d), after: (m, d) => pinTip(m.querySelectorAll(".chart .col")[d.hoverCol]) },
  "rename": { render: (d) => detail(d) + modal("Rename machine", `<div class="field"><label for="rn">Machine name</label><input id="rn" class="in" value="${esc(d.renameTo)}" autofocus><small class="faint">Past runs and the audit log show the new name.</small></div>`, `<a class="btn" href="#detail">Cancel</a><button class="btn primary" data-act="rename">Save name</button>`) },
  "job-rejected": { render: (d) => detail(d, `<div class="banner err">${I.warn}<div><b>Job rejected by ${esc(d.machine.name)}.</b> <span class="mono">${esc(d.machine.rejectError)}</span></div></div>`) },
  "offline": { render: offline },
  "empty": { render: empty },
  "revoke-confirm": { render: (d) => detail(d) + modal(`Revoke ${esc(d.machine.name)}?`, `<p style="margin-top:0">Its token stops working at once. The running job is cancelled and its queued job goes back to the cycle. Past results stay.</p>`, `<a class="btn" href="#detail">Cancel</a><button class="btn danger" data-act="revoke">Revoke machine</button>`) }
}};
