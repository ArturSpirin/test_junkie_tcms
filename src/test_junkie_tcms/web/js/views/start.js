/* Start a cycle: the four-step wizard (what to test, how to run, who runs it) and the live cycle it starts.
   The data and the writes are data/start.js; each step's picks travel in the URL (d.query), so every step is
   loaded from the server. */
import { I, crumbs, modal, footBar, dd, tg, bar, st, actor, esc } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/start.js";

const mst = (s) => `<span class="mst ${s}">${s}</span>`;
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const STEPS = ["What to test", "How to run", "Who runs it", "Results"];
const steps = (cur) => `<ol class="steps">${STEPS.map((s, i) => `<li class="${i < cur ? "done" : i === cur ? "on" : ""}"><span class="no">${i < cur ? "✓" : i + 1}</span><span class="lb">${s}</span></li>`).join("")}</ol>`;
const prodLabel = (d) => esc(`${d.product.key} · ${d.product.name}`);
const prodHref = (d) => href("products", { product: d.product.key, id: d.product.key });
/* this wizard with the picks so far, changed by change, at step ui */
const go = (d, ui, change = {}) => href("start", { product: d.product.key, ...d.query, ...change }, ui);
const scopeUi = (d) => (d.query.features ? "scope-features" : "scope");
const pageHead = (d, cur) => head("Start a cycle", `Run · ${prodLabel(d)}`, crumbs([[prodLabel(d), prodHref(d)], ["Run"], ["Start a cycle"]]),
  `<a class="btn" href="${href("cycles", { product: d.product.key })}">${I.cycle}All cycles</a>`) + steps(cur);
const pick = (o) => { const tag = o.href ? "a" : "div"; return `<${tag}${o.href ? ` href="${o.href}"` : ""}${o.data || ""} class="pick${o.box ? " box" : ""}${o.on ? " on" : ""}${o.dis ? " dis" : ""}" role="${o.box ? "checkbox" : "radio"}" aria-checked="${!!o.on}"${o.dis ? ' aria-disabled="true"' : ""} tabindex="0"><span class="pi">${o.icon}</span><span class="m"><b>${o.t}</b><small>${o.s}</small></span><span class="ck">${I.check}</span></${tag}>`; };
/* foot is a footBar(actions, note) */
const card = (title, body, foot, r = "") => `<div class="card flowc"><div class="hd"><h2>${title}</h2>${r ? `<span class="r">${r}</span>` : ""}</div><div class="bd">${body}</div>${foot || ""}</div>`;
const summary = (d, extra = "") => `<div class="summary"><span class="k">Product</span><b>${prodLabel(d)}</b><span class="faint">·</span><span class="k">Version</span><b>${esc(d.version)}</b><span class="faint">·</span><span class="k">Plan</span><b>${esc(d.plan.name)}</b><span class="faint">·</span><span class="k">Cases</span><b>${d.plan.cases}</b><span class="muted">${d.plan.automated} automated, ${d.plan.manual} manual</span>${extra}</div>`;
const modeChip = (label) => `<span class="faint">·</span><span class="k">Mode</span><b>${label}</b>`;
const tester = (d, h) => (d.testers.find((t) => t.handle === h) || { name: h }).name;
const firstName = (d, h) => tester(d, h).split(" ")[0];
const testerOpt = (t) => ({ v: t.handle, label: t.name, hint: t.role, icon: I.person });
/* a box pick's link: the list of picked ids with id toggled */
const toggle = (ids, id) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]).join(",") || null;

/* step 1: what to test */
function scope(d, by) {
  const mark = (p) => `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>`;
  const prodVer = `<div class="grid2"><div class="field"><label>Product</label>${dd({ value: d.product.key, options: d.products.map((p) => ({ v: p.key, label: `${p.key} · ${p.name}`, icon: mark(p) })), w: "100%", label: "Product", name: "sprod" })}</div>
    <div class="field"><label>Version</label>${dd({ value: d.versionId, options: [{ group: `${d.product.key} versions` }, ...d.versions.map((v) => ({ v: v.id, label: v.ver, hint: v.hint, icon: I.tag }))], w: "100%", label: "Version", name: "sver" })}</div></div>`;
  const seg = `<div class="field"><label>Test</label><div class="seg" role="group" aria-label="Test"><button class="${by === "plan" ? "on" : ""}" aria-pressed="${by === "plan"}" data-href="${esc(go(d, "scope", { features: null }))}">${I.flag} A test plan</button><button class="${by !== "plan" ? "on" : ""}" aria-pressed="${by !== "plan"}" data-href="${esc(go(d, "scope-features", { plan: null }))}">${I.folder} Pick features</button></div></div>`;
  const on = d.features.filter((f) => f.on);
  const ids = on.map((f) => f.id);
  const picks = by === "plan"
    ? `<div class="field"><label>Test plan for ${esc(d.version)}</label><div class="picks c2">${d.plans.map((p) => pick({ icon: I.flag, t: esc(p.name), s: p.cantRun ? esc(p.meta) + " · can’t run" : esc(p.meta), on: p.on, dis: p.cantRun, href: p.cantRun ? "" : go(d, "scope", { plan: p.id, features: null }) })).join("")}</div></div>`
    : `<div class="field"><label>Features in ${esc(d.version)}</label><div class="picks c2">${d.features.map((f) => pick({ box: true, icon: I.folder, t: esc(f.path), s: f.cases + " cases", on: f.on, href: go(d, "scope-features", { plan: null, features: toggle(ids, f.id) }) })).join("")}</div></div>`;
  const n = by === "plan" ? `${d.plan.name} · ${d.plan.cases} cases` : `${on.length} features · ${on.reduce((a, f) => a + f.cases, 0)} cases`;
  return pageHead(d, 0) + card("What do you want to test?", prodVer + seg + picks,
    footBar(`<a class="btn" href="${href("plans", { product: d.product.key })}">Cancel</a><a class="btn primary" href="${go(d, "mode")}">Continue${I.chev}</a>`, n));
}

/* step 2: how to run; the picks carry the environment and cycle name to the next step */
function mode(d, sel) {
  const p = d.plan;
  const env = `<div class="grid2"><div class="field"><label>Environment</label>${dd({ value: d.environment, options: d.environments.map((e) => ({ v: e, label: e, icon: I.server })), w: "100%", label: "Environment", name: "env" })}</div>
    <div class="field"><label for="cn">Cycle name</label><input id="cn" class="in" value="${esc(d.cycleName)}"></div></div>`;
  const ms = [["manual", I.person, "Manual", `A person runs all ${p.cases} cases on the run screen, one by one.`, "mode-manual"], ["auto", I.server, "Automated", `Paired machines run the ${p.automated} automated cases. The ${p.manual} manual cases stay untested.`, "mode"], ["mixed", I.members, "Both", `Machines run the ${p.automated} automated cases; a person runs the ${p.manual} manual ones at the same time.`, "mode-mixed"]];
  const next = sel === "manual" ? "manual-ready" : sel === "mixed" ? "mixed-pick" : "auto-pick";
  return pageHead(d, 1) + card("How should it run?", summary(d) + env + `<div class="field"><label>Run mode</label><div class="picks">${ms.map((m) => pick({ icon: m[1], t: m[2], s: m[3], on: m[0] === sel, href: go(d, m[4]), data: ` data-carry="${m[4]}"` })).join("")}</div></div>`,
    footBar(`<a class="btn" href="${go(d, scopeUi(d))}">Back</a><a class="btn primary" href="${go(d, next)}" data-carry="${next}">Continue${I.chev}</a>`, `Creates the cycle and pins ${p.cases} cases at their current version`));
}

/* step 3a: manual (v5: no "Notify the tester") */
const manualReady = (d) => pageHead(d, 2) + card("Who runs it?", summary(d, modeChip("Manual")) +
  `<div class="grid2"><div class="field"><label>Tester</label>${dd({ value: d.tester, options: [...d.testers.map(testerOpt), "-", { v: "none", label: "Leave unassigned", hint: "anyone with tester role can pick it up" }], w: "100%", label: "Tester", name: "tester" })}</div>
  <div class="field"><label>Order</label>${dd({ value: d.order, options: [{ v: "feature", label: "By feature, then priority" }, { v: "priority", label: "Priority first" }, { v: "plan", label: "As listed in the plan" }], w: "100%", label: "Order", name: "order" })}</div></div>`,
  footBar(`<a class="btn" href="${go(d, "mode-manual")}">Back</a><button class="btn primary" data-act="start" data-mode="manual">${I.play}Start manual run</button>`));

/* step 3b: automated, pick machines, how the cases split across them and how often a failed case retries */
const allowed = (m) => m.allowed !== false;
const runOpts = (d, none) => `<div class="grid2"><div class="field"><label>Split cases</label>${dd({ value: d.split, options: [{ v: "by_feature", label: "By feature", hint: "each machine takes whole features" }, { v: "even", label: "Evenly by count" }, { v: "first_free", label: "All on the first free machine" }], w: "100%", label: "Split cases", name: "split", dis: none })}</div>
    <div class="field"><label>Retries</label>${dd({ value: String(d.retries), options: [{ v: "0", label: "No retries" }, { v: "1", label: "Retry a failed case once" }, { v: "2", label: "Retry twice" }], w: "100%", label: "Retries", name: "retries", dis: none })}</div></div>
    <div class="tg-list" style="margin-bottom:16px">${tg(false, "Queue on offline machines", "picked machines that are offline take their jobs when they come back", { name: "offline", disabled: none })}</div>`;
const autoPick = (d, mixed, ui) => {
  const key = esc(d.product.key);
  const none = !d.machines.some((m) => m.status !== "offline");
  const ids = d.machines.filter((m) => m.on).map((m) => m.id);
  const machPick = (m) => {
    const dis = none || !allowed(m) || m.status === "offline";
    return pick({ box: true, icon: I.server, t: `${esc(m.name)} &nbsp;${mst(m.status)}`, s: esc(m.meta), on: !none && m.on, dis, href: dis ? "" : go(d, ui, { machines: toggle(ids, m.id) }) });
  };
  const ban = none ? `<div class="banner warn" style="margin-bottom:16px">${I.wifioff}<div style="flex:1"><b>No machines online for ${key}.</b> Machines paired for ${key}: ${esc(d.machines.filter(allowed).map((m) => m.name).join(", "))}.${d.heartbeatWindow ? ` None has sent a heartbeat in the last ${esc(d.heartbeatWindow)}.` : ""}</div></div>` : "";
  const foot = none
    ? footBar(`<a class="btn" href="${href("consumers", {}, "pair")}">${I.plus}Pair a machine</a><a class="btn" href="${go(d, "manual-ready")}">Run manually instead</a>`)
    : footBar(`<a class="btn" href="${go(d, mixed ? "mode-mixed" : "mode")}">Back</a><button class="btn primary" data-act="start" data-mode="${mixed ? "mixed" : "auto"}">${I.play}Start run on ${ids.length} machines</button>`);
  return pageHead(d, 2) + card("Which machines run it?", summary(d, modeChip(mixed ? "Both" : "Automated")) + ban +
    `<div class="field"><label>Machines paired for ${key}</label><div class="picks c2">${d.machines.map(machPick).join("")}</div></div>` + runOpts(d, none) +
    (mixed ? `<div class="field"><label>Tester for the ${d.plan.manual} manual cases</label>${dd({ value: d.tester, options: d.testers.filter((t) => d.mixedTesters.includes(t.handle)).map(testerOpt), w: "min(100%, 360px)", label: "Tester", name: "tester" })}</div>` : ""), foot,
    `<a class="btn sm" href="${href("consumers")}">${I.server}Machines</a>`);
};

/* step 4: live */
const resTable = (d, c) => `<div class="tbl-wrap"><table class="t"><thead><tr><th>Case</th><th class="hide-n">Machine</th><th>Status</th><th class="hide-n">Time</th></tr></thead><tbody>${c.results.map((r) => {
  const s = r.status === "running" ? `<span class="mst busy">running</span>` : (c.stalled && r.machine === c.stalled.machine && r.status === "untested") ? `<span class="chip">waiting</span>` : st(c.finished && (r.status === "running" || r.status === "untested") ? "success" : r.status);
  return `<tr><td><a href="${href("case", { product: d.product.key, id: r.key })}"><b class="mono">${esc(r.key)}</b></a><span class="ell muted">${esc(r.title)}</span></td><td class="hide-n">${esc(r.machine)}</td><td>${s}</td><td class="hide-n mono">${esc(r.time)}</td></tr>`;
}).join("")}</tbody></table></div>`;
const jobRow = (c, j) => {
  const name = `<b>${I.server}<span class="ell">${esc(j.machine)}</span></b>`;
  const pct = Math.round((j.done / j.total) * 100);
  const s = c.stalled && c.stalled.machine === j.machine ? c.stalled : null;
  if (s) return `<div class="qrow">${name}${mst("offline")}<small>${esc(j.features)} · ${j.done} of ${j.total} done · no heartbeat for ${esc(s.since)}, ${s.waiting} cases waiting</small><div class="prog stall"><i style="width:${pct}%"></i></div><div class="acts">${s.reassignTo ? `<button class="btn sm primary" data-act="reassign">Reassign to ${esc(s.reassignTo)}</button>` : ""}<a class="btn sm" href="#offline-mid">Wait for it</a><a class="btn sm" href="#cancel-cases">Cancel its ${s.waiting} cases</a></div></div>`;
  const w = c.queued ? 0 : c.finished ? 100 : pct;
  return `<div class="qrow">${name}${c.finished ? mst("online") : mst("busy")}<small>${esc(j.features)} · ${c.finished ? j.total : j.done} of ${j.total} done</small><div class="prog${c.finished ? " done" : ""}"><i style="width:${w}%"></i></div></div>`;
};
function live(d) {
  const c = d.cycle, fin = c.finished, mixed = c.mode === "mixed", m = c.manual;
  const key = esc(d.product.key), ver = esc(d.version), name = esc(c.name);
  const at = { product: d.product.key };
  const cycleHref = href("cycles", { ...at, id: c.id });
  const pill = c.stopped ? '<span class="pill closed">stopped</span>' : fin ? '<span class="pill closed">finished</span>' : '<span class="pill in_progress">running</span>';
  const fails = esc(c.failedKeys.join(", "));
  const kp = fin
    ? [["Automated", `${c.done} of ${c.total}`, `finished in ${esc(c.elapsed)}`], ["Passed", c.passed, `${c.passedPct}% of automated`], ["Failed or error", c.failed, fails], ["Manual", `${m.count} untested`, mixed ? `assigned to ${esc(tester(d, c.manualTester))}` : "not assigned yet"]]
    : [["Done", `${c.done} of ${c.total}`, "automated cases"], ["Passed", c.passed, `${c.passedPct}% so far`], ["Failed or error", c.failed, fails], ["Elapsed", esc(c.elapsed), c.left ? `about ${esc(c.left)} left` : ""]];
  const kpis = `<div class="kpis">${kp.map((k) => `<div class="kpi"><span class="l">${k[0]}</span><span class="v">${k[1]}</span><span class="d">${k[2]}</span></div>`).join("")}</div>`;
  const queue = `<div class="card"><div class="hd"><h2>Job queue</h2><span class="r faint" style="font-size:12px">${c.jobs.length} machines</span></div>
    ${c.jobs.map((j) => jobRow(c, j)).join("")}</div>`;
  const who = mixed ? esc(firstName(d, c.manualTester)) : "";
  const more = m.count - m.cases.length;
  const manual = mixed ? `<div class="card gap"><div class="hd"><h2>Manual cases</h2><span class="r">${actor("person", c.manualTester)}</span></div>
    <div class="lrow"><span class="pi">${I.person}</span><span class="m"><b>${m.count} manual cases · ${fin ? `${m.count} untested` : `${m.done} of ${m.count} done`}</b><small>${m.cases.map((x) => esc(`${x.key} ${x.title}`)).join(", ")}${more > 0 ? `, and ${more} more` : ""}. ${who} runs them while the machines work.</small></span><span class="r"><a class="btn sm primary" href="${href("run", { ...at, id: c.id })}">${I.play}Open manual run</a></span></div></div>` : "";
  const stallJob = c.stalled && c.jobs.find((j) => j.machine === c.stalled.machine);
  const ban = c.stopped ? `<div class="banner info" style="margin-bottom:16px">${I.x}<div style="flex:1"><b>Run stopped${c.stoppedBy ? ` by ${esc(c.stoppedBy)}` : ""}.</b> Queued cases were cancelled; running cases finish and their results stay in the cycle. <a href="${cycleHref}">Open cycle</a></div></div>`
    : c.stalled ?`<div class="banner warn" style="margin-bottom:16px">${I.wifioff}<div style="flex:1"><b>${esc(c.stalled.machine)} stopped sending heartbeats ${esc(c.stalled.since)} ago.</b> Its ${c.stalled.waiting} remaining ${esc(stallJob.features)} cases are on hold. Reassign them, wait for it to come back, or cancel them.</div></div>`
    : fin ? `<div class="banner info" style="margin-bottom:16px">${I.check}<div style="flex:1"><b>Automated run finished.</b> ${c.counts.success || 0} passed, ${c.counts.fail || 0} failed, ${c.counts.error || 0} error. ${mixed ? `${who}’s ${m.count} manual cases are still open, so the cycle stays open.` : `${m.count} manual cases are untested; the cycle stays open until they’re run or skipped.`} <a href="${cycleHref}">Open cycle</a> · <a href="${href("reports", at)}">Report</a></div></div>`
    : c.queued ? `<div class="banner info" style="margin-bottom:16px">${I.clock}<div style="flex:1"><b>Cycle created; ${c.jobs.length} jobs queued.</b> They start when a machine paired for ${key} picks them up. <a href="${href("consumers")}">Machines</a></div></div>`
    : "";
  const relCrumb = d.releaseId ? [[ver, href("releases", { ...at, id: d.releaseId })]] : [];
  return head(name, `Cycle · ${key} ${ver} · ${mixed ? "Both" : "Automated"}`, crumbs([[prodLabel(d), prodHref(d)], ...relCrumb, ["Cycles", href("cycles", at)], [name]]),
    `${pill}<a class="btn" href="${cycleHref}">${I.cycle}Open cycle</a>${fin || c.stopped ? "" : `<a class="btn" href="#stop-confirm">${I.x}Stop run</a>`}`) + steps(fin ? 4 : 3) + ban + kpis +
    `<div style="margin:20px 0">${bar(c.counts, "", name)}</div>` + manual +
    `<div class="g2 stack-l">${queue}<div class="card"><div class="hd"><h2>Latest results</h2><span class="r faint" style="font-size:12px">${fin ? `${c.done} of ${c.total}` : `live · ${c.done} of ${c.total}`}</span></div>${resTable(d, c)}</div></div>`;
}

const cancelCases = (d) => {
  const s = d.cycle.stalled, j = d.cycle.jobs.find((x) => x.machine === s.machine);
  return modal(esc(`Cancel ${s.waiting} cases on ${s.machine}?`), `<p style="margin-top:0">The ${s.waiting} cases waiting on this machine are marked <b>cancel</b> and nobody runs them. The ${j.done} finished results stay in the cycle. Start a new cycle later to run them.</p>`,
    `<a class="btn" href="#offline-mid">Keep waiting</a><button class="btn danger" data-act="cancel-job">Cancel ${s.waiting} cases</button>`);
};
const stopConfirm = (d) => modal("Stop this run?", `<p style="margin-top:0">Running cases finish; the ${d.cycle.total - d.cycle.done} queued cases are cancelled and marked <b>cancel</b>. Results so far stay in the cycle.</p>`,
  `<button class="btn" data-back>Keep running</button><button class="btn danger" data-act="stop">Stop run</button>`);

/* the real controls: picks are links (the next load reads them), dropdowns and buttons write through data/start.js */
const picked = (main, name) => { const o = main.querySelector(`[data-name="${name}"] .dd-o.sel`); return o ? o.dataset.v : ""; };
const errAt = (btn) => { const m = btn.closest(".modal"); if (m) return m.querySelector(".mb"); const c = btn.closest(".card"); return c.querySelector(":scope > .bd") || c; };
const MODE_OF = { manual: "manual", auto: "auto", mixed: "mixed" };

function after(main, state, d) {
  main.querySelectorAll("[data-href]").forEach((b) => b.addEventListener("click", () => location.assign(b.dataset.href)));
  main.addEventListener("dd:change", (e) => {
    if (e.detail.name === "sprod") location.assign(href("start", { product: e.detail.value }, "scope"));
    if (e.detail.name === "sver") location.assign(go(d, scopeUi(d), { version: e.detail.value, plan: null, features: null, machines: null }));
  });
  /* step 2: a mode pick or Continue takes the environment and the cycle name along */
  main.querySelectorAll("a[data-carry]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    const name = main.querySelector("#cn");
    location.assign(go(d, a.dataset.carry, { env: picked(main, "env") || null, name: name && name.value.trim() !== d.cycleName ? name.value.trim() : d.query.name }));
  }));
  const start = main.querySelector("[data-act=start]");
  if (start) start.addEventListener("click", async () => {
    start.disabled = true;
    const form = {
      plan: d.query.plan, features: d.query.features ? d.query.features.split(",") : [], release: d.versionId,
      name: d.cycleName, environment: d.environment, mode: MODE_OF[start.dataset.mode],
      tester: picked(main, "tester") || d.tester, order: picked(main, "order") || d.order,
      machines: d.machines.filter((m) => m.on).map((m) => m.id),
      split: picked(main, "split") || d.split, retries: picked(main, "retries") || String(d.retries),
      offline: !!(main.querySelector("input[name=offline]") || {}).checked
    };
    try {
      const c = await actions.start(form, d.ctx, d.product.key);
      location.assign(form.mode === "manual" ? href("run", { product: d.product.key, id: c.id }) : href("start", { product: d.product.key, id: c.id }));
    } catch (e) { showError(errAt(start), e, "Couldn't start the cycle."); start.disabled = false; }
  });
  const s = d.cycle && d.cycle.stalled;
  const reassign = main.querySelector("[data-act=reassign]");
  if (reassign && s) reassign.addEventListener("click", async () => {
    reassign.disabled = true;
    try {
      await actions.reassign(s.jobId, s.reassignId, d.ctx);
      location.assign(href("start", { product: d.product.key, id: d.cycle.id, moved: s.waiting, to: s.reassignTo }, "reassigned"));
    } catch (e) { showError(errAt(reassign), e, "Couldn't reassign the job."); reassign.disabled = false; }
  });
  const cancel = main.querySelector("[data-act=cancel-job]");
  if (cancel && s) cancel.addEventListener("click", async () => {
    cancel.disabled = true;
    try {
      await actions.cancel(s.jobId, d.ctx);
      location.assign(href("start", { product: d.product.key, id: d.cycle.id }));
    } catch (e) { showError(errAt(cancel), e, "Couldn't cancel the cases."); cancel.disabled = false; }
  });
  const stop = main.querySelector("[data-act=stop]");
  if (stop && d.cycle) stop.addEventListener("click", async () => {
    stop.disabled = true;
    try {
      await actions.stop(d.cycle.id, d.ctx);
      location.assign(href("start", { product: d.product.key, id: d.cycle.id }));
    } catch (e) { showError(errAt(stop), e, "Couldn't stop the run."); stop.disabled = false; }
  });
}

export default { nav: "run", default: "scope", after, states: {
  "scope": { render: (d) => scope(d, "plan") },
  "scope-features": { render: (d) => scope(d, "features") },
  "mode": { render: (d) => mode(d, "auto") },
  "mode-manual": { render: (d) => mode(d, "manual") },
  "mode-mixed": { render: (d) => mode(d, "mixed") },
  "manual-ready": { render: manualReady },
  "auto-pick": { render: (d) => autoPick(d, false, "auto-pick") },
  "mixed-pick": { render: (d) => autoPick(d, true, "mixed-pick") },
  "auto-none": { render: (d) => autoPick(d, false, "auto-pick") },
  "queued": { render: live },
  "live": { render: live },
  "offline-mid": { render: live },
  "reassigned": { render: live, toast: (d) => `<div><b>${d.moved.count} cases moved to ${esc(d.moved.to)}.</b> <span class="muted">They run after its current job.</span></div>` },
  "mixed": { render: live },
  "cancel-cases": { render: (d) => live(d) + cancelCases(d) },
  "stop-confirm": { render: (d) => live(d) + stopConfirm(d) },
  "done": { render: live },
  "done-mixed": { render: live }
}};
