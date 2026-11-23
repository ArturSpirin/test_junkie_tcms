/* Start a cycle: the four-step wizard (what to test, how to run, who runs it) and the live cycle it starts. */
import { I, crumbs, lnk, modal, dd, tg, bar, st, actor, toast, esc } from "../ui.js";

const mst = (s) => `<span class="mst ${s}">${s}</span>`;
const head = (title, eyebrow, c, act) => `${c}<div class="ph"><div class="ttl"><span class="eyebrow">${eyebrow}</span><h1>${title}</h1></div><div class="actions">${act || ""}</div></div>`;
const STEPS = ["What to test", "How to run", "Who runs it", "Results"];
const steps = (cur) => `<ol class="steps">${STEPS.map((s, i) => `<li class="${i < cur ? "done" : i === cur ? "on" : ""}"><span class="no">${i < cur ? "✓" : i + 1}</span><span class="lb">${s}</span></li>`).join("")}</ol>`;
const prodLabel = (d) => esc(`${d.product.key} · ${d.product.name}`);
const pageHead = (d, cur) => head("Start a cycle", `Run · ${prodLabel(d)}`, crumbs([[prodLabel(d), "products.html#detail"], ["Run"], ["Start a cycle"]]),
  `<a class="btn" href="${lnk("cycles.html")}">${I.cycle}All cycles</a>`) + steps(cur);
const pick = (o) => { const tag = o.href ? "a" : "div"; return `<${tag}${o.href ? ` href="${o.href}"` : ""} class="pick${o.box ? " box" : ""}${o.on ? " on" : ""}${o.dis ? " dis" : ""}" role="${o.box ? "checkbox" : "radio"}" aria-checked="${!!o.on}"${o.dis ? ' aria-disabled="true"' : ""} tabindex="0"><span class="pi">${o.icon}</span><span class="m"><b>${o.t}</b><small>${o.s}</small></span><span class="ck">${I.check}</span></${tag}>`; };
const card = (title, body, foot, r = "") => `<div class="card flowc"><div class="hd"><h2>${title}</h2>${r ? `<span class="r">${r}</span>` : ""}</div><div class="bd">${body}</div>${foot ? `<div class="foot-bar">${foot}</div>` : ""}</div>`;
const summary = (d, extra = "") => `<div class="summary"><span class="k">Product</span><b>${prodLabel(d)}</b><span class="faint">·</span><span class="k">Version</span><b>${esc(d.version)}</b><span class="faint">·</span><span class="k">Plan</span><b>${esc(d.plan.name)}</b><span class="faint">·</span><span class="k">Cases</span><b>${d.plan.cases}</b><span class="muted">${d.plan.automated} automated, ${d.plan.manual} manual</span>${extra}</div>`;
const modeChip = (label) => `<span class="faint">·</span><span class="k">Mode</span><b>${label}</b>`;
const tester = (d, h) => (d.testers.find((t) => t.handle === h) || { name: h }).name;
const firstName = (d, h) => tester(d, h).split(" ")[0];
const testerOpt = (t) => ({ v: t.handle, label: t.name, hint: t.role, icon: I.person });

/* step 1: what to test */
function scope(d, by) {
  const mark = (p) => `<span class="mark xs${p.markCls ? " " + p.markCls : ""}">${esc(p.key[0])}</span>`;
  const prodVer = `<div class="grid2"><div class="field"><label>Product</label>${dd({ value: d.product.key, options: d.products.map((p) => ({ v: p.key, label: `${p.key} · ${p.name}`, icon: mark(p) })), w: "100%", label: "Product" })}</div>
    <div class="field"><label>Version</label>${dd({ value: d.version, options: [{ group: `${d.product.key} versions` }, ...d.versions.map((v) => ({ v: v.ver, label: v.ver, hint: v.hint, icon: I.tag }))], w: "100%", label: "Version" })}</div></div>`;
  const seg = `<div class="field"><label>Test</label><div class="seg" role="group" aria-label="Test"><button class="${by === "plan" ? "on" : ""}" aria-pressed="${by === "plan"}" data-go="#scope">${I.flag} A test plan</button><button class="${by !== "plan" ? "on" : ""}" aria-pressed="${by !== "plan"}" data-go="#scope-features">${I.folder} Pick features</button></div></div>`;
  const picks = by === "plan"
    ? `<div class="field"><label>Test plan for ${esc(d.version)}</label><div class="picks c2">${d.plans.map((p) => pick({ icon: I.flag, t: esc(p.name), s: p.cantRun ? esc(p.meta) + " · can’t run" : esc(p.meta), on: p.on, dis: p.cantRun })).join("")}</div></div>`
    : `<div class="field"><label>Features in ${esc(d.version)}</label><div class="picks c2">${d.features.map((f) => pick({ box: true, icon: I.folder, t: esc(f.path), s: f.cases + " cases", on: f.on })).join("")}</div></div>`;
  const on = d.features.filter((f) => f.on);
  const n = by === "plan" ? `${esc(d.plan.name)} · ${d.plan.cases} cases` : `${on.length} features · ${on.reduce((a, f) => a + f.cases, 0)} cases`;
  return pageHead(d, 0) + card("What do you want to test?", prodVer + seg + picks,
    `<span class="l">${n}</span><a class="btn" href="${lnk("plans.html")}">Cancel</a><a class="btn primary" href="#mode">Continue${I.chev}</a>`);
}

/* step 2: how to run */
function mode(d, sel) {
  const p = d.plan;
  const env = `<div class="grid2"><div class="field"><label>Environment</label>${dd({ value: d.environment, options: d.environments.map((e) => ({ v: e, label: e, icon: I.server })), w: "100%", label: "Environment" })}</div>
    <div class="field"><label for="cn">Cycle name</label><input id="cn" class="in" value="${esc(d.cycleName)}"></div></div>`;
  const ms = [["manual", I.person, "Manual", `A person runs all ${p.cases} cases on the run screen, one by one.`, "#mode-manual"], ["auto", I.server, "Automated", `Paired machines run the ${p.automated} automated cases. The ${p.manual} manual cases stay untested.`, "#mode"], ["mixed", I.members, "Both", `Machines run the ${p.automated} automated cases; a person runs the ${p.manual} manual ones at the same time.`, "#mode-mixed"]];
  const next = sel === "manual" ? "#manual-ready" : sel === "mixed" ? "#mixed-pick" : "#auto-pick";
  return pageHead(d, 1) + card("How should it run?", summary(d) + env + `<div class="field"><label>Run mode</label><div class="picks">${ms.map((m) => pick({ icon: m[1], t: m[2], s: m[3], on: m[0] === sel, href: m[4] })).join("")}</div></div>`,
    `<span class="l">Creates the cycle and pins ${p.cases} cases at their current version</span><a class="btn" href="#scope">Back</a><a class="btn primary" href="${next}">Continue${I.chev}</a>`);
}

/* step 3a: manual */
const manualReady = (d) => pageHead(d, 2) + card("Who runs it?", summary(d, modeChip("Manual")) +
  `<div class="grid2"><div class="field"><label>Tester</label>${dd({ value: d.tester, options: [...d.testers.map(testerOpt), "-", { v: "none", label: "Leave unassigned", hint: "anyone with tester role can pick it up" }], w: "100%", label: "Tester" })}</div>
  <div class="field"><label>Order</label>${dd({ value: "feature", options: [{ v: "feature", label: "By feature, then priority" }, { v: "priority", label: "Priority first" }, { v: "plan", label: "As listed in the plan" }], w: "100%", label: "Order" })}</div></div>
  ${tg(true, "Notify the tester", `${esc(firstName(d, d.tester))} gets a notification with a link to the run screen`)}`,
  `<span class="l mono">POST /cycles  ${esc(JSON.stringify({ plan_id: d.plan.id, environment: d.environment }))}</span><a class="btn" href="#mode-manual">Back</a><a class="btn primary" href="${lnk("run.html")}">${I.play}Start manual run</a>`);

/* step 3b: automated, pick machines */
const allowed = (m) => m.allowed !== false;
const machPick = (m, none) => pick({ box: true, icon: I.server, t: `${esc(m.name)} &nbsp;${mst(m.status)}`, s: esc(m.meta), on: !none && m.on, dis: none || !allowed(m) || m.status === "offline" });
const autoPick = (d, mixed) => {
  const key = esc(d.product.key);
  const none = !d.machines.some((m) => m.status !== "offline");
  const ban = none ? `<div class="banner warn" style="margin-bottom:16px">${I.wifioff}<div style="flex:1"><b>No machines online for ${key}.</b> Machines paired for ${key}: ${esc(d.machines.filter(allowed).map((m) => m.name).join(", "))}. None has sent a heartbeat in the last ${esc(d.heartbeatWindow)}.</div></div>` : "";
  const foot = none
    ? `<span class="l">You can still create the cycle; its ${d.plan.automated} jobs wait until a machine comes online.</span><a class="btn" href="${lnk("consumers.html#pair")}">${I.plus}Pair a machine</a><a class="btn" href="#manual-ready">Run manually instead</a><a class="btn primary" href="#queued">Create cycle and queue jobs</a>`
    : `<span class="l mono">POST /cycles/{id}/jobs</span><a class="btn" href="#mode">Back</a><a class="btn primary" href="#${mixed ? "mixed" : "live"}">${I.play}Start run on ${d.machines.filter((m) => m.on).length} machines</a>`;
  return pageHead(d, 2) + card("Which machines run it?", summary(d, modeChip(mixed ? "Both" : "Automated")) + ban +
    `<div class="field"><label>Machines paired for ${key}</label><div class="picks c2">${d.machines.map((m) => machPick(m, none)).join("")}</div></div>
    <div class="grid2"><div class="field"><label>Split cases</label>${dd({ value: "feature", options: [{ v: "feature", label: "By feature", hint: "each machine takes whole features" }, { v: "even", label: "Evenly by count" }, { v: "one", label: "All on the first free machine" }], w: "100%", label: "Split cases", dis: none })}</div>
    <div class="field"><label>Retries</label>${dd({ value: "1", options: [{ v: "0", label: "No retries" }, { v: "1", label: "Retry a failed case once" }, { v: "2", label: "Retry twice" }], w: "100%", label: "Retries", dis: none })}</div></div>` +
    (mixed ? `<div class="field"><label>Tester for the ${d.plan.manual} manual cases</label>${dd({ value: d.tester, options: d.testers.filter((t) => d.mixedTesters.includes(t.handle)).map(testerOpt), w: "min(100%, 360px)", label: "Tester" })}</div>` : ""), foot,
    `<a class="btn sm" href="${lnk("consumers.html")}">${I.server}Machines</a>`);
};

/* step 4: live */
const resTable = (c) => `<div class="tbl-wrap"><table class="t"><thead><tr><th>Case</th><th class="hide-n">Machine</th><th>Status</th><th class="hide-n">Time</th></tr></thead><tbody>${c.results.map((r) => {
  const s = r.status === "running" ? `<span class="mst busy">running</span>` : (c.stalled && r.machine === c.stalled.machine && r.status === "untested") ? `<span class="chip">waiting</span>` : st(c.finished && (r.status === "running" || r.status === "untested") ? "success" : r.status);
  return `<tr><td><a href="${lnk("case.html")}"><b class="mono">${esc(r.key)}</b></a><span class="ell muted">${esc(r.title)}</span></td><td class="hide-n">${esc(r.machine)}</td><td>${s}</td><td class="hide-n mono">${esc(r.time)}</td></tr>`;
}).join("")}</tbody></table></div>`;
const jobRow = (c, j) => {
  const name = `<b>${I.server}<span class="ell">${esc(j.machine)}</span></b>`;
  const pct = Math.round((j.done / j.total) * 100);
  const s = c.stalled && c.stalled.machine === j.machine ? c.stalled : null;
  if (s) return `<div class="qrow">${name}${mst("offline")}<small>${esc(j.features)} · ${j.done} of ${j.total} done · no heartbeat for ${esc(s.since)}, ${s.waiting} cases waiting</small><div class="prog stall"><i style="width:${pct}%"></i></div><div class="acts"><a class="btn sm primary" href="#reassigned">Reassign to ${esc(s.reassignTo)}</a><a class="btn sm" href="#offline-mid">Wait for it</a><a class="btn sm" href="#cancel-cases">Cancel its ${s.waiting} cases</a></div></div>`;
  const w = c.queued ? 0 : c.finished ? 100 : pct;
  return `<div class="qrow">${name}${c.finished ? mst("online") : mst("busy")}<small>${esc(j.features)} · ${c.finished ? j.total : j.done} of ${j.total} done</small><div class="prog${c.finished ? " done" : ""}"><i style="width:${w}%"></i></div></div>`;
};
function live(d) {
  const c = d.cycle, fin = c.finished, mixed = c.mode === "mixed", m = c.manual;
  const key = esc(d.product.key), ver = esc(d.version), name = esc(c.name);
  const pill = fin ? '<span class="pill closed">finished</span>' : '<span class="pill in_progress">running</span>';
  const fails = esc(c.failedKeys.join(", "));
  const kp = fin
    ? [["Automated", `${c.done} of ${c.total}`, `finished in ${esc(c.elapsed)}`], ["Passed", c.passed, `${c.passedPct}% of automated`], ["Failed or error", c.failed, fails], ["Manual", `${m.count} untested`, mixed ? `assigned to ${esc(tester(d, c.manualTester))}` : "not assigned yet"]]
    : [["Done", `${c.done} of ${c.total}`, "automated cases"], ["Passed", c.passed, `${c.passedPct}% so far`], ["Failed or error", c.failed, fails], ["Elapsed", esc(c.elapsed), `about ${esc(c.left)} left`]];
  const kpis = `<div class="kpis">${kp.map((k) => `<div class="kpi"><span class="l">${k[0]}</span><span class="v">${k[1]}</span><span class="d">${k[2]}</span></div>`).join("")}</div>`;
  const queue = `<div class="card"><div class="hd"><h2>Job queue</h2><span class="r faint" style="font-size:12px">${c.jobs.length} machines</span></div>
    ${c.jobs.map((j) => jobRow(c, j)).join("")}</div>`;
  const who = mixed ? esc(firstName(d, c.manualTester)) : "";
  const manual = mixed ? `<div class="card gap"><div class="hd"><h2>Manual cases</h2><span class="r">${actor("person", c.manualTester)}</span></div>
    <div class="lrow"><span class="pi">${I.person}</span><span class="m"><b>${m.count} manual cases · ${fin ? `${m.count} untested` : `${m.done} of ${m.count} done`}</b><small>${m.cases.map((x) => esc(`${x.key} ${x.title}`)).join(", ")}, and ${m.count - m.cases.length} more. ${who} runs them while the machines work.</small></span><span class="r"><a class="btn sm primary" href="${lnk("run.html")}">${I.play}Open manual run</a></span></div></div>` : "";
  const stallJob = c.stalled && c.jobs.find((j) => j.machine === c.stalled.machine);
  const ban = c.stalled ? `<div class="banner warn" style="margin-bottom:16px">${I.wifioff}<div style="flex:1"><b>${esc(c.stalled.machine)} stopped sending heartbeats ${esc(c.stalled.since)} ago.</b> Its ${c.stalled.waiting} remaining ${esc(stallJob.features)} cases are on hold. Reassign them, wait for it to come back, or cancel them.</div></div>`
    : fin ? `<div class="banner info" style="margin-bottom:16px">${I.check}<div style="flex:1"><b>Automated run finished.</b> ${c.counts.success} passed, ${c.counts.fail} failed, ${c.counts.error} error. ${mixed ? `${who}’s ${m.count} manual cases are still open, so the cycle stays open.` : `${m.count} manual cases are untested; the cycle stays open until they’re run or skipped.`} <a href="${lnk("cycles.html#detail")}">Open cycle</a> · <a href="${lnk("reports.html")}">Report</a></div></div>`
    : c.queued ? `<div class="banner info" style="margin-bottom:16px">${I.clock}<div style="flex:1"><b>Cycle created; ${c.total} jobs queued.</b> They start when a machine paired for ${key} comes online. <a href="${lnk("consumers.html")}">Machines</a></div></div>`
    : "";
  return head(name, `Cycle · ${key} ${ver} · ${mixed ? "Both" : "Automated"}`, crumbs([[prodLabel(d), "products.html#detail"], [ver, "releases.html#detail"], ["Cycles", "cycles.html"], [name]]),
    `${pill}<a class="btn" href="${lnk("cycles.html#detail")}">${I.cycle}Open cycle</a>${fin ? "" : `<a class="btn" href="#stop-confirm">${I.x}Stop run</a>`}`) + steps(fin ? 4 : 3) + ban + kpis +
    `<div style="margin:20px 0">${bar(c.counts, "", name)}</div>` + manual +
    `<div class="g2 stack-l">${queue}<div class="card"><div class="hd"><h2>Latest results</h2><span class="r faint" style="font-size:12px">${fin ? `${c.done} of ${c.total}` : `live · ${c.done} of ${c.total}`}</span></div>${resTable(c)}</div></div>`;
}

const cancelCases = (d) => {
  const s = d.cycle.stalled, j = d.cycle.jobs.find((x) => x.machine === s.machine);
  return modal(esc(`Cancel ${s.waiting} cases on ${s.machine}?`), `<p style="margin-top:0">The ${s.waiting} cases waiting on this machine are marked <b>cancel</b> and nobody runs them. The ${j.done} finished results stay in the cycle. Start a new cycle later to run them.</p>`,
    `<span class="l mono">POST /cycles/${esc(d.cycle.id)}/jobs:cancel</span><a class="btn" href="#offline-mid">Keep waiting</a><a class="btn danger" href="#live">Cancel ${s.waiting} cases</a>`);
};
const stopConfirm = (d) => modal("Stop this run?", `<p style="margin-top:0">Running cases finish; the ${d.cycle.total - d.cycle.done} queued cases are cancelled and marked <b>cancel</b>. Results so far stay in the cycle.</p>`,
  `<span class="l mono">POST /cycles/${esc(d.cycle.id)}/jobs:cancel</span><button class="btn" data-back>Keep running</button><button class="btn danger">Stop run</button>`);

/* the step 1 segmented control switches state */
const after = (main) => main.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.go; }));

export default { nav: "run", default: "scope", after, states: {
  "scope": { render: (d) => scope(d, "plan") },
  "scope-features": { render: (d) => scope(d, "features") },
  "mode": { render: (d) => mode(d, "auto") },
  "mode-manual": { render: (d) => mode(d, "manual") },
  "mode-mixed": { render: (d) => mode(d, "mixed") },
  "manual-ready": { render: manualReady },
  "auto-pick": { render: (d) => autoPick(d, false) },
  "mixed-pick": { render: (d) => autoPick(d, true) },
  "auto-none": { render: (d) => autoPick(d, false) },
  "queued": { render: live },
  "live": { render: live },
  "offline-mid": { render: live },
  "reassigned": { render: live, after: (m, d) => toast(`<div><b>${d.moved.count} cases moved to ${esc(d.moved.to)}.</b> <span class="muted">They run after its current job.</span></div>`) },
  "mixed": { render: live },
  "cancel-cases": { render: (d) => live(d) + cancelCases(d) },
  "stop-confirm": { render: (d) => live(d) + stopConfirm(d) },
  "done": { render: live },
  "done-mixed": { render: live }
}};
