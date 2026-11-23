/* Run: the manual run screen. A queue of cases, the current case with its steps and keyboard result entry.
   The data and the writes are data/run.js. */
import { I, st, disc, ver, modal, dd, toast, bar, STATUS, esc, person } from "../ui.js";
import { href, showError } from "../shell.js";
import { actions } from "../data/run.js";

/* Test Junkie statuses (test_junkie/constants.py:3-11) with their run-screen keys */
const TJ = ["success", "fail", "error", "ignore", "skip", "cancel"];
const KEY = { success: "1", fail: "2", error: "3", ignore: "4", skip: "5", cancel: "6" };
/* the statuses a step result can have (StepResultIn); per-step ignore and cancel are not served yet (F4) */
const STEP = TJ.filter((s) => !["ignore", "cancel"].includes(s));
const ICON = (s) => STATUS.find((x) => x[0] === s)[2];
/* data options name their icon; the dropdown wants the svg */
const opts = (list) => list.map((o) => (o === "-" || o.group ? o : { ...o, icon: I[o.icon] }));
/* per-state view flags: the skip reason list open, a file dragged over the drop zone */
const FLAGS = { "skip-reason": { skipOpen: true }, drop: { drop: true } };
const at = (d) => ({ product: d.product.key });

/* the run model: which step is current, the step results, what each failed step carries (actual, defect, the
   files attached) and the view flags; keys() mutates it as the tester works */
const model = (d, flags = {}) => ({ cur: d.current.step, res: [...d.current.res], q: d.current.q, actual: {}, du: {}, dk: {}, files: {}, ...flags });

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
const kb = (n) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);
function queue(d, cur) {
  const c = d.cycle, left = d.queue.filter((q) => q.status === "untested").length;
  const meta = [c.version, c.environment].filter(Boolean).map(esc).join(" · ");
  return `<aside class="queue"><div class="qh"><div class="eyebrow">Queue</div><div class="row" style="margin-top:6px"><b class="ell">${esc(c.queue)}</b></div><div class="muted" style="font-size:12px;margin-top:2px">${meta ? meta + " · " : ""}${left ? `${left} of ${d.queue.length} left` : `all ${d.queue.length} done`}</div><div style="margin-top:12px">${bar(tally(d.queue))}</div></div>
  ${d.queue.map((q, i) => { const s = d.queueOver[i] || q.status; return `<div class="qi ${i === cur ? "on" : ""}" title="${s}">${disc(i + 1, i === cur ? "cur" : s)}<span class="ell">${esc(q.title)}</span>${s !== "untested" ? st(s, { label: false }).replace('class="st ', 'class="st dotonly ') : '<span></span>'}<span class="key">${esc(q.key)}</span></div>`; }).join("")}</aside>`;
}
function rstep(d, s, i, o) {
  const v = o.res[i] || "";
  const cur = i === o.cur;
  const f = d.failure;
  const files = f.files.concat(o.files[i] || []);
  let xtra = "";
  if (v === "fail") xtra = `<div class="xtra">
    <div class="field mb0"><label for="act${i}">Actual result</label><textarea id="act${i}" class="in" rows="2" data-f="actual">${esc(o.actual[i] ?? f.actual)}</textarea></div>
    <div><span class="mini-lbl">Evidence</span><div class="row wrap">${files.map((a) => `<span class="att">${I.clip}${esc(a.name)} <span class="faint">${esc(a.size)}</span></span>`).join("")}</div>
      <div class="drop ${o.drop ? "over" : ""}" style="margin-top:10px">${I.upload} ${o.drop ? "<b>Drop to attach to step " + (i + 1) + "</b>" : "Drop files or paste a screenshot (Ctrl+V)"}</div>${d.uploadError ? uploadErr(d.uploadError) : ""}</div>
    <div class="grid2"><div class="field mb0"><label for="du${i}">Defect URL</label><input id="du${i}" class="in" data-f="du" value="${esc(o.du[i] ?? f.defectUrl)}"></div><div class="field mb0"><label for="dk${i}">Defect key</label><input id="dk${i}" class="in mono" data-f="dk" value="${esc(o.dk[i] ?? f.defectKey)}"></div></div></div>`;
  else if (v === "skip" && d.skipReasons) xtra = `<div class="xtra"><div class="grid2"><div class="field mb0"><label>Skip reason <span class="muted">required</span></label>${dd({ value: d.skip.reason, options: opts(d.skipReasons), cls: "block", open: !!o.skipOpen, label: "Skip reason", hl: o.skipOpen ? "env" : undefined })}<span class="hint">Test Junkie has no “blocked” status: a blocked step is a skip with a reason.</span></div>
    <div class="field mb0"><label for="bk${i}">Blocking defect <span class="muted">optional</span></label><input id="bk${i}" class="in mono" value="${esc(d.skip.blockingDefect)}" placeholder="LAB-412"></div></div></div>`;
  const pill = v ? st(v) : cur ? "" : st("untested");
  return `<div class="rstep ${cur ? "cur" : ""}" data-i="${i}">${disc(i + 1, cur && !v ? "cur" : v || "untested")}
  <div class="shd"><span class="eyebrow">Step ${i + 1}</span><span class="sid">${esc(s.id)}</span><span class="r">${pill}${cur ? '<span class="chip acc">Current</span>' : ""}</span></div>
  <div class="rich" style="grid-column:2"><span class="mini-lbl">Action</span>${s.action}</div><div class="rich ex"><span class="mini-lbl">Expected</span>${s.expected}</div>
  <div class="sbtns" role="group" aria-label="Step ${i + 1} result">${STEP.map((k) => `<button class="sbtn ${k} ${v === k ? "on" : ""}" data-k="${k}" title="${k} (${KEY[k]})" aria-pressed="${v === k}">${ICON(k)}<span class="hide-n">${k}</span><kbd class="hide-n">${KEY[k]}</kbd></button>`).join("")}</div>${xtra}</div>`;
}
const uploadErr = (e) => `<div class="banner err" style="margin:10px 0 0">${I.warn}<div style="flex:1;min-width:0"><b>${esc(e.file)} not attached.</b>
<pre class="raw">${esc(e.raw)}</pre></div></div>`;
const caseDd = (d) => dd({ value: d.case.key, cls: "block", label: "Case", name: "case", options: [{ group: `${d.cycle.queue} · ${d.queue.length} cases` }].concat(d.queue.map((q, i) => ({ v: q.key, label: `${q.key} · ${q.title}`, short: `${q.key} · ${q.title}`, hint: d.queueOver[i] || q.status, dot: `var(--st-${d.queueOver[i] || q.status})` }))) });
const steps = (d, o) => d.case.steps.map((s, i) => rstep(d, s, i, o)).join("");
function run(d, o) {
  const c = d.case, n = d.queue.length, p = d.previous;
  const prev = p ? [p.note ? `“${esc(p.note)}”` : "", p.defectKey ? esc(p.defectKey) : "", p.fixedIn ? `fixed in build ${esc(p.fixedIn)}` : ""].filter(Boolean).join(" · ") : "";
  return `<div class="runlay">${queue(d, o.q)}<div class="runmain">
  <div class="only-n" style="margin-bottom:16px"><span class="mini-lbl">Case ${o.q + 1} of ${n} · ${esc(d.cycle.queue)}</span>${caseDd(d)}</div>
  <div class="eyebrow hide-n">Case ${o.q + 1} of ${n}</div>
  <div class="case-hd"><span class="key">${esc(c.key)}</span>${ver(c.pin, 1)}<span class="faint" style="font-size:12px">case_version pinned in this cycle${c.newer ? " · v" + c.newer + " exists" : ""}</span>${c.attempt > 1 ? `<span class="chip acc">${I.restore}attempt ${c.attempt}</span>` : '<span class="chip">attempt 1</span>'}
    ${d.builds ? dd({ value: c.build, options: opts(d.builds), cls: "sm", pre: "Build", label: "Build under test" }) : ""}</div>
  <h1>${esc(c.title)}</h1>
  ${c.attempt > 1 && p ? `<div class="banner info">${I.restore}<div>This is <b>attempt ${c.attempt}</b>. Attempt ${c.attempt - 1} ${st(p.status)} by ${esc(person(p.by)[0])}, ${esc(p.at)}${prev ? `: ${prev}` : ""}. Attempt ${c.attempt - 1} stays in the history.</div></div>` : ""}
  ${c.preconditions ? `<details class="card pre-card"><summary><span class="eyebrow">Preconditions</span><span class="muted" style="font-weight:400;font-size:13px">${esc(c.preShort)}</span><span class="dd-c">${I.chevd}</span></summary><div class="bd rich">${esc(c.preconditions)}</div></details>` : ""}
  <div class="kbar"><span><kbd>j</kbd>/<kbd>k</kbd> next/prev case</span><span><kbd>↓</kbd>/<kbd>↑</kbd> step</span><span><kbd>1</kbd>–<kbd>3</kbd>, <kbd>5</kbd> success, fail, error, skip</span><span><kbd>a</kbd> actual</span><span><kbd>Ctrl</kbd>+<kbd>Enter</kbd> submit</span><span><kbd>?</kbd> all keys</span></div>
  <div id="steps">${steps(d, o)}</div>
  <div class="field" style="margin-top:16px"><label for="cm">Comment</label><textarea id="cm" class="in" rows="2" placeholder="Optional"></textarea></div>
  <div class="runfoot"><span class="row"><span class="mini-lbl" style="margin:0">Case result</span><span id="overall">${st(overall(d, o.res), { lg: 1 })}</span></span><span class="faint" style="font-size:12px">attempt ${c.attempt} · <span id="el">${esc(c.elapsed || "00:00")}</span> elapsed</span><span style="flex:1"></span>
    <button class="btn ghost" data-go="help"><kbd>?</kbd> Keys</button><button class="btn primary" data-act="submit">Submit and next <kbd style="background:none;color:inherit;border-color:currentColor;box-shadow:none">Ctrl+↵</kbd></button></div>
  </div></div>`;
}
function complete(d) {
  const c = tally(d.queue);
  const sum = STATUS.filter((s) => c[s[0]]).map((s) => st(s[0], { label: `${c[s[0]]} ${s[0]}` })).join("");
  const report = href("reports", { ...at(d), level: "product", release: d.cycle.releaseId || null });
  return `<div class="runlay">${queue(d, -1)}<div class="runmain"><div class="eyebrow hide-n">Cycle ${esc(d.cycle.id)} · finished</div><h1 style="margin-bottom:16px">Run complete</h1><div class="card lift"><div class="empty"><div class="ill">${I.check}</div><h3>All ${d.queue.length} cases have a result</h3>
  <div>${[d.cycle.queue, d.cycle.version, d.cycle.environment].filter(Boolean).map(esc).join(" · ")}</div>
  <div class="res-sum">${sum}</div>
  <div style="max-width:360px;margin:16px auto 0">${bar(c, "lg")}</div>
  <a class="btn" href="${href("cycles", { ...at(d), id: d.cycle.id })}">Back to cycle</a> <a class="btn primary" href="${report}">Release report</a></div></div></div></div>`;
}
/* the toast after a save; undo is not served yet (F4) */
const saved = (s) => `<div class="toast" role="status"><div class="row wrap"><b>${esc(s.key)}</b>${st(s.status)}<span class="muted">attempt ${s.attempt} · ${s.defects} defect · ${s.files} files · saved via ${esc(s.via)}</span></div></div>`;

/* a dropped or pasted file as AttachmentBase64In */
const read = (file) => new Promise((ok, no) => {
  const r = new FileReader();
  r.onload = () => ok({ filename: file.name, mime: file.type || undefined, content_base64: String(r.result).replace(/^data:[^,]*,/, "") });
  r.onerror = () => no(r.error);
  r.readAsDataURL(file);
});

/* the ResultCreate this screen sends: the case result, the comment, each step's result (a failed one with its
   actual result and files) and the defects the failed steps name */
function body(main, d, o, ms) {
  const comment = main.querySelector("#cm").value.trim();
  const defects = [];
  const stepsIn = d.case.steps.map((s, i) => {
    const out = { step_id: s.id, status: o.res[i] || "untested" };
    if (o.res[i] === "fail") {
      const actual = (o.actual[i] ?? "").trim();
      if (actual) out.actual = { markdown: actual };
      out.attachment_ids = (o.files[i] || []).map((a) => a.id);
      const url = (o.du[i] ?? "").trim(), key = (o.dk[i] ?? "").trim();
      if (url) defects.push(key ? { url, key } : { url });
    }
    return out;
  });
  return { status: overall(d, o.res), ...(comment ? { comment: { markdown: comment } } : {}), duration_ms: ms, steps: stepsIn, defects };
}

/* step clicks, drag and drop, the keyboard and the writes; o is this render's model */
let timer = null;
function keys(main, o, d) {
  clearInterval(timer);
  main.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.go; }));
  const box = main.querySelector("#steps"); if (!box) { document.onkeydown = null; return; }
  const started = Date.now();
  const el = main.querySelector("#el");
  timer = setInterval(() => {
    if (!el.isConnected) { clearInterval(timer); return; }
    const s = Math.floor((Date.now() - started) / 1000);
    el.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
  const n = d.case.steps.length;
  const draw = () => { box.innerHTML = steps(d, o); main.querySelector("#overall").innerHTML = st(overall(d, o.res), { lg: 1 }); };
  const go = (i) => { o.cur = Math.max(0, Math.min(n - 1, i)); draw(); box.children[o.cur].scrollIntoView({ block: "nearest" }); };
  const set = (i, k) => { o.res[i] = k; o.skipOpen = false; if (k === "fail" || k === "skip") { o.cur = i; draw(); } else go(i + 1); };
  const toCase = (i) => { if (d.queue[i]) location.assign(href("run", { ...at(d), id: d.cycle.id, cc: d.queue[i].id })); };
  box.addEventListener("click", (e) => { const b = e.target.closest(".sbtn"); if (b) { set(+b.closest(".rstep").dataset.i, b.dataset.k); return; } const r = e.target.closest(".rstep"); if (r && !e.target.closest(".xtra") && +r.dataset.i !== o.cur) go(+r.dataset.i); });
  box.addEventListener("input", (e) => { const f = e.target.dataset.f; if (f) o[f][+e.target.closest(".rstep").dataset.i] = e.target.value; });
  /* evidence: each file is uploaded, then named on the step's result when it is submitted */
  const attach = async (i, files) => {
    for (const file of files) {
      try {
        const a = await actions.attach(d.product.key, await read(file), d.ctx);
        (o.files[i] = o.files[i] || []).push({ id: a.id, name: a.filename, size: kb(a.size) });
        draw();
        toast(`<div><b>Attached to step ${i + 1}.</b></div>`);
      } catch (err) {
        const zone = box.children[i].querySelector(".drop");
        if (zone) zone.insertAdjacentHTML("afterend", uploadErr({ file: file.name, raw: err.raw ?? String(err) }));
        else showError(main, err, `${file.name} not attached.`);
      }
    }
  };
  box.addEventListener("dragover", (e) => { const z = e.target.closest(".drop"); if (z) { e.preventDefault(); z.classList.add("over"); } });
  box.addEventListener("dragleave", (e) => { const z = e.target.closest(".drop"); if (z) z.classList.remove("over"); });
  box.addEventListener("drop", (e) => { const z = e.target.closest(".drop"); if (z) { e.preventDefault(); z.classList.remove("over"); attach(+z.closest(".rstep").dataset.i, [...e.dataTransfer.files]); } });
  box.addEventListener("paste", (e) => { const r = e.target.closest(".rstep"); const files = [...(e.clipboardData ? e.clipboardData.files : [])]; if (r && files.length && o.res[+r.dataset.i] === "fail") { e.preventDefault(); attach(+r.dataset.i, files); } });
  const nar = main.querySelector('[data-name="case"]');
  if (nar) nar.addEventListener("dd:change", (e) => toCase(d.queue.findIndex((q) => q.key === e.detail.value)));
  const btn = main.querySelector("[data-act=submit]");
  const submit = async () => {
    if (btn.disabled) return;
    btn.disabled = true;
    try {
      await actions.submit(d.case.id, body(main, d, o, Date.now() - started), d.ctx);
      location.assign(href("run", { ...at(d), id: d.cycle.id, done: d.case.id }, "submitted"));
    } catch (err) {
      showError(main.querySelector(".runmain"), err, "Couldn't save the result.");
      btn.disabled = false;
    }
  };
  btn.addEventListener("click", submit);
  document.onkeydown = (e) => {
    if ((/INPUT|TEXTAREA/.test(e.target.tagName) || e.target.closest(".dd")) && !(e.ctrlKey && e.key === "Enter")) return;
    const k = STEP.find((s) => KEY[s] === e.key);
    if (k) { set(o.cur, k); e.preventDefault(); }
    else if (e.key === "ArrowDown") { go(o.cur + 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { go(o.cur - 1); e.preventDefault(); }
    else if (e.key === "j" || e.key === "k") toCase(o.q + (e.key === "j" ? 1 : -1));
    else if (e.key === "a") { const a = main.querySelector(`#act${o.cur}`); if (a) { a.focus(); e.preventDefault(); } }
    else if (e.key === "?") location.hash = "help";
    else if (e.key === "Escape" && location.hash === "#help") history.back();
    else if (e.ctrlKey && e.key === "Enter") { e.preventDefault(); submit(); }
  };
}
const help = () => modal("Keyboard", `<table class="t help-ov"><tbody>
  ${[["j / k", "Next / previous case in the queue"], ["↓ / ↑", "Next / previous step"]].concat(STEP.map((s) => [KEY[s], `Step ${st(s)} and move on${s === "fail" ? " (opens actual result and evidence)" : ""}`])).concat([["a", "Write the actual result for this step"], ["Ctrl + V", "Paste a screenshot as evidence"], ["Ctrl + Enter", "Submit the result and open the next untested case"], ["?", "This list"], ["Esc", "Close"]]).map((r) => `<tr><td><kbd>${r[0]}</kbd></td><td>${r[1]}</td></tr>`).join("")}
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
