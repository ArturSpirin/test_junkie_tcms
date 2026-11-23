/* Run: the manual run screen. A queue of cases, the current case with its steps and keyboard result entry. */
import { I, st, disc, ver, modal, dd, toast, bar, STATUS, esc, lnk, person } from "../ui.js";

/* Test Junkie statuses (test_junkie/constants.py:3-11) with their run-screen keys */
const TJ = ["success", "fail", "error", "ignore", "skip", "cancel"];
const KEY = { success: "1", fail: "2", error: "3", ignore: "4", skip: "5", cancel: "6" };
const ICON = (s) => STATUS.find((x) => x[0] === s)[2];
/* data options name their icon; the dropdown wants the svg */
const opts = (list) => list.map((o) => (o === "-" || o.group ? o : { ...o, icon: I[o.icon] }));
/* per-state view flags: the skip reason list open, a file dragged over the drop zone */
const FLAGS = { "skip-reason": { skipOpen: true }, drop: { drop: true } };

/* the run model: which step is current, the step results and the view flags; keys() mutates it as the tester works */
const model = (d, flags = {}) => ({ cur: d.current.step, res: [...d.current.res], q: d.current.q, ...flags });

function overall(d, res) {
  const v = Object.values(res);
  if (v.includes("fail")) return "fail";
  if (v.includes("error")) return "error";
  if (v.length < d.case.steps.length) return "untested";
  for (const s of ["cancel", "skip"]) if (v.includes(s)) return s;
  if (v.every((x) => x === "ignore")) return "ignore";
  return "success";
}
const tally = (list) => list.reduce((c, q) => ({ ...c, [q.status]: (c[q.status] || 0) + 1 }), {});
function queue(d, cur) {
  const c = d.cycle, left = d.queue.filter((q) => q.status === "untested").length;
  return `<aside class="queue"><div class="qh"><div class="eyebrow">Queue</div><div class="row" style="margin-top:6px"><b class="ell">${esc(c.queue)}</b></div><div class="muted" style="font-size:12px;margin-top:2px">${esc(c.version)} · ${esc(c.environment)} · ${left ? `${left} of ${d.queue.length} left` : `all ${d.queue.length} done`}</div><div style="margin-top:12px">${bar(tally(d.queue))}</div></div>
  ${d.queue.map((q, i) => { const s = d.queueOver[i] || q.status; return `<div class="qi ${i === cur ? "on" : ""}" title="${s}">${disc(i + 1, i === cur ? "cur" : s)}<span class="ell">${esc(q.title)}</span>${s !== "untested" ? st(s, { label: false }).replace('class="st ', 'class="st dotonly ') : '<span></span>'}<span class="key">${esc(q.key)}</span></div>`; }).join("")}</aside>`;
}
function rstep(d, s, i, o) {
  const v = o.res[i] || "";
  const cur = i === o.cur;
  const f = d.failure;
  let xtra = "";
  if (v === "fail") xtra = `<div class="xtra">
    <div class="field mb0"><label for="act${i}">Actual result</label><textarea id="act${i}" class="in" rows="2">${esc(f.actual)}</textarea></div>
    <div><span class="mini-lbl">Evidence</span><div class="row wrap">${f.files.map((a) => `<span class="att">${I.clip}${esc(a.name)} <span class="faint">${esc(a.size)}</span></span>`).join("")}</div>
      <div class="drop ${o.drop ? "over" : ""}" style="margin-top:10px">${I.upload} ${o.drop ? "<b>Drop to attach to step " + (i + 1) + "</b>" : "Drop files or paste a screenshot (Ctrl+V)"}</div>${d.uploadError ? uploadErr(d.uploadError) : ""}</div>
    <div class="grid2"><div class="field mb0"><label for="du${i}">Defect URL</label><input id="du${i}" class="in" value="${esc(f.defectUrl)}"></div><div class="field mb0"><label for="dk${i}">Defect key</label><input id="dk${i}" class="in mono" value="${esc(f.defectKey)}"></div></div></div>`;
  else if (v === "skip") xtra = `<div class="xtra"><div class="grid2"><div class="field mb0"><label>Skip reason <span class="muted">required</span></label>${dd({ value: d.skip.reason, options: opts(d.skipReasons), cls: "block", open: !!o.skipOpen, label: "Skip reason", hl: o.skipOpen ? "env" : undefined })}<span class="hint">Test Junkie has no “blocked” status: a blocked step is a skip with a reason.</span></div>
    <div class="field mb0"><label for="bk${i}">Blocking defect <span class="muted">optional</span></label><input id="bk${i}" class="in mono" value="${esc(d.skip.blockingDefect)}" placeholder="LAB-412"></div></div></div>`;
  const pill = v ? st(v) : cur ? "" : st("untested");
  return `<div class="rstep ${cur ? "cur" : ""}" data-i="${i}">${disc(i + 1, cur && !v ? "cur" : v || "untested")}
  <div class="shd"><span class="eyebrow">Step ${i + 1}</span><span class="sid">${esc(s.id)}</span><span class="r">${pill}${cur ? '<span class="chip acc">Current</span>' : ""}</span></div>
  <div class="rich" style="grid-column:2"><span class="mini-lbl">Action</span>${s.action}</div><div class="rich ex"><span class="mini-lbl">Expected</span>${s.expected}</div>
  <div class="sbtns" role="group" aria-label="Step ${i + 1} result">${TJ.map((k) => `<button class="sbtn ${k} ${v === k ? "on" : ""}" data-k="${k}" title="${k} (${KEY[k]})" aria-pressed="${v === k}">${ICON(k)}<span class="hide-n">${k}</span><kbd class="hide-n">${KEY[k]}</kbd></button>`).join("")}</div>${xtra}</div>`;
}
const uploadErr = (e) => `<div class="banner err" style="margin:10px 0 0">${I.warn}<div style="flex:1;min-width:0"><b>${esc(e.file)} not attached.</b>
<pre class="raw">${esc(e.raw)}</pre></div></div>`;
const caseDd = (d) => dd({ value: d.case.key, cls: "block", label: "Case", options: [{ group: `${d.cycle.queue} · ${d.queue.length} cases` }].concat(d.queue.map((q, i) => ({ v: q.key, label: `${q.key} · ${q.title}`, short: `${q.key} · ${q.title}`, hint: d.queueOver[i] || q.status, dot: `var(--st-${d.queueOver[i] || q.status})` }))) });
const steps = (d, o) => d.case.steps.map((s, i) => rstep(d, s, i, o)).join("");
function run(d, o) {
  const c = d.case, n = d.queue.length, p = d.previous;
  return `<div class="runlay">${queue(d, o.q)}<div class="runmain">
  <div class="only-n" style="margin-bottom:16px"><span class="mini-lbl">Case ${o.q + 1} of ${n} · ${esc(d.cycle.queue)}</span>${caseDd(d)}</div>
  <div class="eyebrow hide-n">Case ${o.q + 1} of ${n}</div>
  <div class="case-hd"><span class="key">${esc(c.key)}</span>${ver(c.pin, 1)}<span class="faint" style="font-size:12px">case_version pinned in this cycle${c.newer ? " · v" + c.newer + " exists" : ""}</span>${c.attempt > 1 ? `<span class="chip acc">${I.restore}attempt ${c.attempt}</span>` : '<span class="chip">attempt 1</span>'}
    ${dd({ value: c.build, options: opts(d.builds), cls: "sm", pre: "Build", label: "Build under test" })}</div>
  <h1>${esc(c.title)}</h1>
  ${c.attempt > 1 && p ? `<div class="banner info">${I.restore}<div>This is <b>attempt ${c.attempt}</b>. Attempt ${c.attempt - 1} ${st(p.status)} by ${esc(person(p.by)[0])}, ${esc(p.at)}: “${esc(p.note)}” · ${esc(p.defectKey)} fixed in build ${esc(p.fixedIn)}. Attempt ${c.attempt - 1} stays in the history.</div></div>` : ""}
  <details class="card pre-card"><summary><span class="eyebrow">Preconditions</span><span class="muted" style="font-weight:400;font-size:13px">${esc(c.preShort)}</span><span class="dd-c">${I.chevd}</span></summary><div class="bd rich">${esc(c.preconditions)}</div></details>
  <div class="kbar"><span><kbd>j</kbd>/<kbd>k</kbd> next/prev case</span><span><kbd>↓</kbd>/<kbd>↑</kbd> step</span><span><kbd>1</kbd>–<kbd>6</kbd> success, fail, error, ignore, skip, cancel</span><span><kbd>a</kbd> actual</span><span><kbd>Ctrl</kbd>+<kbd>Enter</kbd> submit</span><span><kbd>?</kbd> all keys</span></div>
  <div id="steps">${steps(d, o)}</div>
  <div class="field" style="margin-top:16px"><label for="cm">Comment</label><textarea id="cm" class="in" rows="2" placeholder="Optional"></textarea></div>
  <div class="runfoot"><span class="row"><span class="mini-lbl" style="margin:0">Case result</span><span id="overall">${st(overall(d, o.res), { lg: 1 })}</span></span><span class="faint" style="font-size:12px">attempt ${c.attempt} · ${esc(c.elapsed)} elapsed</span><span style="flex:1"></span>
    <button class="btn ghost" data-go="help"><kbd>?</kbd> Keys</button><button class="btn primary" data-go="submitted">Submit and next <kbd style="background:none;color:inherit;border-color:currentColor;box-shadow:none">Ctrl+↵</kbd></button></div>
  </div></div>`;
}
function complete(d) {
  const c = tally(d.queue);
  const sum = STATUS.filter((s) => c[s[0]]).map((s) => st(s[0], { label: `${c[s[0]]} ${s[0]}` })).join("");
  return `<div class="runlay">${queue(d, -1)}<div class="runmain"><div class="eyebrow hide-n">Cycle ${esc(d.cycle.id)} · finished</div><h1 style="margin-bottom:16px">Run complete</h1><div class="card lift"><div class="empty"><div class="ill">${I.check}</div><h3>All ${d.queue.length} cases have a result</h3>
  <div>${esc(d.cycle.queue)} · ${esc(d.cycle.version)} · ${esc(d.cycle.environment)}</div>
  <div class="res-sum">${sum}</div>
  <div style="max-width:360px;margin:16px auto 0">${bar(c, "lg")}</div>
  <a class="btn" href="${lnk("cycles.html#detail")}">Back to cycle</a> <a class="btn primary" href="${lnk("reports.html#product")}">Release report</a></div></div></div></div>`;
}
const saved = (s) => `<div class="toast" role="status"><div class="row wrap"><b>${esc(s.key)}</b>${st(s.status)}<span class="muted">attempt ${s.attempt} · ${s.defects} defect · ${s.files} files · saved via ${esc(s.via)}</span></div><a href="#step-failed">Undo</a></div>`;

/* step clicks, drag and drop and the keyboard; o is this render's model */
function keys(main, o, d) {
  main.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.go; }));
  const box = main.querySelector("#steps"); if (!box) { document.onkeydown = null; return; }
  const n = d.case.steps.length;
  const draw = () => { box.innerHTML = steps(d, o); main.querySelector("#overall").innerHTML = st(overall(d, o.res), { lg: 1 }); };
  const go = (i) => { o.cur = Math.max(0, Math.min(n - 1, i)); draw(); box.children[o.cur].scrollIntoView({ block: "nearest" }); };
  const set = (i, k) => { o.res[i] = k; o.skipOpen = false; if (k === "fail" || k === "skip") { o.cur = i; draw(); } else go(i + 1); };
  box.addEventListener("click", (e) => { const b = e.target.closest(".sbtn"); if (b) { set(+b.closest(".rstep").dataset.i, b.dataset.k); return; } const r = e.target.closest(".rstep"); if (r && !e.target.closest(".xtra") && +r.dataset.i !== o.cur) go(+r.dataset.i); });
  box.addEventListener("dragover", (e) => { const z = e.target.closest(".drop"); if (z) { e.preventDefault(); z.classList.add("over"); } });
  box.addEventListener("dragleave", (e) => { const z = e.target.closest(".drop"); if (z) z.classList.remove("over"); });
  box.addEventListener("drop", (e) => { const z = e.target.closest(".drop"); if (z) { e.preventDefault(); z.classList.remove("over"); toast("<div><b>Attached to step " + (o.cur + 1) + ".</b></div>"); } });
  document.onkeydown = (e) => {
    if ((/INPUT|TEXTAREA/.test(e.target.tagName) || e.target.closest(".dd")) && !(e.ctrlKey && e.key === "Enter")) return;
    const k = TJ.find((s) => KEY[s] === e.key);
    if (k) { set(o.cur, k); e.preventDefault(); }
    else if (e.key === "ArrowDown") { go(o.cur + 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { go(o.cur - 1); e.preventDefault(); }
    else if (e.key === "j" || e.key === "k") { const qs = [...main.querySelectorAll(".qi")], at = qs.findIndex((x) => x.classList.contains("on")), m = Math.max(0, Math.min(qs.length - 1, at + (e.key === "j" ? 1 : -1))); qs.forEach((x, j) => x.classList.toggle("on", j === m)); }
    else if (e.key === "?") location.hash = "help";
    else if (e.key === "Escape" && location.hash === "#help") history.back();
    else if (e.ctrlKey && e.key === "Enter") location.hash = "submitted";
  };
}
const help = () => modal("Keyboard", `<table class="t help-ov"><tbody>
  ${[["j / k", "Next / previous case in the queue"], ["↓ / ↑", "Next / previous step"]].concat(TJ.map((s) => [KEY[s], `Step ${st(s)} and move on${s === "skip" ? " (asks for a reason)" : s === "fail" ? " (opens actual result and evidence)" : ""}`])).concat([["a", "Write the actual result for this step"], ["u", "Attach a file to this step"], ["d", "Add a defect (URL and key)"], ["Ctrl + V", "Paste a screenshot as evidence"], ["Ctrl + Enter", "Submit the result and open the next untested case"], ["?", "This list"], ["Esc", "Close"]]).map((r) => `<tr><td><kbd>${r[0]}</kbd></td><td>${r[1]}</td></tr>`).join("")}
  </tbody></table>`, "");

const view = (d, id) => run(d, model(d, FLAGS[id]));
export default { nav: "run", flush: true, default: "in-progress", after: (main, id, d) => keys(main, model(d, FLAGS[id]), d), states: {
  "in-progress": { render: (d) => view(d, "in-progress") },
  "step-failed": { render: (d) => view(d, "step-failed") },
  "skip-reason": { render: (d) => view(d, "skip-reason") },
  "drop": { render: (d) => view(d, "drop") },
  "help": { render: (d) => view(d, "help") + help() },
  "submitted": { render: (d) => view(d, "submitted") + saved(d.saved) },
  "retest": { render: (d) => view(d, "retest") },
  "upload-error": { render: (d) => view(d, "upload-error") },
  "complete": { render: complete }
}};
