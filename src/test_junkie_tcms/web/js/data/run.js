/* Run adapter (docs/app-api-contract.md §10): cycles_get, cycle_cases_list (the queue, in run order),
   cases_version_get (the pinned version's steps as the stored doc, drawn as HTML, and its preconditions),
   results_list (attempts so far), releases_get for the version label and cycle_builds (the builds under test
   recorded for the product, newest first). Writes: results_create (with every Test Junkie step status, the skip
   reason and the build) and attachments_upload_base64. Result undo is not in the API yet.
   URL: ?view=run&id=<cycle>[&cc=<cycle case>][&done=<cycle case just saved>]#<ui>. With no cc the case is the first
   untested one in run order; none left is "complete". */
import { all, get, org, post } from "../api.js";
import { plain } from "./map.js";

const UI = ["help", "step-failed", "skip-reason", "drop", "upload-error"];

/* a dropdown option; icon is an icon name the view turns into its svg */
const opt = (v, label, hint, icon) => ({ v, label, hint, icon });
/* the skip reasons results_create takes (SKIP_REASONS); "other" needs the comment to say what it is */
const SKIP_REASONS = [
  { group: "Blocked" },
  opt("defect", "Blocked by a defect", "Link the defect below", "ban"),
  opt("env", "Environment down", "the environment or a dependency is down", "server"),
  opt("data", "Test data missing", "an account or fixture is not available", "doc"),
  opt("dep", "Depends on a failed step", "an earlier step failed", "link"),
  { group: "Not applicable" },
  opt("na_env", "Not applicable on this environment", "", "eyeoff"),
  opt("flag", "Feature flag off", "", "flag"),
  "-",
  opt("other", "Other…", "Write the reason in the comment", "more")
];

/* the build dropdown: the builds recorded for the product, newest first, then "not recorded" (no build sent) */
const buildOpts = (builds) => (builds.length ? [{ group: "Recorded builds" }] : [])
  .concat(builds.map((b) => opt(b.build, b.build, `last result ${stamp(b.last_at)}`, "build")), builds.length ? ["-"] : [], [opt("", "Not recorded", "", "dotted")]);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/* ---------- a stored rich-text doc (ProseMirror JSON) as HTML ---------- */
const MARK = { bold: "b", italic: "i", strike: "s", code: "code" };
function inline(n) {
  if (n.type === "hardBreak") return "<br>";
  if (n.type === "image") return `<span class="img">${esc((n.attrs && n.attrs.alt) || "image")}</span>`;
  let s = esc(n.text);
  for (const m of [...(n.marks || [])].reverse()) {
    s = m.type === "link" ? `<a href="${esc(m.attrs.href)}" rel="noopener">${s}</a>` : MARK[m.type] ? `<${MARK[m.type]}>${s}</${MARK[m.type]}>` : s;
  }
  return s;
}
const item = (n) => (n.content && n.content.length === 1 && n.content[0].type === "paragraph" ? (n.content[0].content || []).map(inline).join("") : (n.content || []).map(block).join(""));
function block(n) {
  const kids = () => (n.content || []).map(block).join("");
  switch (n.type) {
    case "paragraph": return `<p>${(n.content || []).map(inline).join("")}</p>`;
    case "heading": return `<h${n.attrs.level}>${(n.content || []).map(inline).join("")}</h${n.attrs.level}>`;
    case "bulletList": return `<ul>${(n.content || []).map((li) => `<li>${item(li)}</li>`).join("")}</ul>`;
    case "orderedList": return `<ol>${(n.content || []).map((li) => `<li>${item(li)}</li>`).join("")}</ol>`;
    case "taskList": return `<ul class="cl">${(n.content || []).map((li) => `<li${li.attrs && li.attrs.checked ? ' class="done"' : ""}>${item(li)}</li>`).join("")}</ul>`;
    case "codeBlock": return `<pre><code>${esc((n.content || []).map((t) => t.text).join(""))}</code></pre>`;
    case "blockquote": return `<blockquote>${kids()}</blockquote>`;
    case "table": return `<table>${(n.content || []).map((tr) => `<tr>${(tr.content || []).map((c) => { const t = c.type === "tableHeader" ? "th" : "td"; return `<${t}>${item(c)}</${t}>`; }).join("")}</tr>`).join("")}</table>`;
    case "horizontalRule": return "<hr>";
    default: return inline(n);
  }
}
/* a doc of one paragraph shows bare, the way a step cell holds one line */
function html(doc) {
  const c = (doc && doc.content) || [];
  if (c.length === 1 && c[0].type === "paragraph") return (c[0].content || []).map(inline).join("");
  return c.map(block).join("");
}

/* "Thu Nov 12, 4:20 PM" in the browser's zone */
const stamp = (iso) => new Date(iso).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).replace(/^(\w+), /, "$1 ");

function productOf(ctx, productId) {
  const p = ctx.products.find((x) => x.id === productId) || ctx.product;
  return { id: p.id, key: p.key, name: p.name };
}

/* the last attempt as the retest banner reads it */
function previous(r) {
  const defect = r.defects.find((x) => x.key || x.url);
  return { status: r.status, by: r.actor_id, at: stamp(r.at), note: plain(r.comment), defectKey: defect ? defect.key || defect.url : "" };
}

/* the toast after a save: the newest attempt of the cycle case just saved */
function savedOf(cc, attempts) {
  const r = attempts[attempts.length - 1];
  const files = new Set([...r.attachment_ids, ...r.steps.flatMap((s) => s.attachment_ids)]);
  return { key: cc.key, status: r.status, attempt: r.attempt, defects: r.defects.length, files: files.size, via: r.via };
}

/* params: the URL query (id: the cycle; cc: the case to run; done: the case just saved) and ui, the hash. */
export async function load(params, ctx) {
  const path = (...rest) => org(ctx.org.id, ...rest);
  const c = await get(path("cycles", params.id));
  const [cases, release, builds] = await Promise.all([
    all(path("cycles", c.id, "cases"), { sort: "position" }),
    c.release_id ? get(path("releases", c.release_id)) : null,
    get(path("cycles", c.id, "builds"))
  ]);
  const data = {
    product: productOf(ctx, c.product_id),
    cycle: { id: c.id, queue: c.name, version: release ? release.version : "", environment: c.environment || "", releaseId: c.release_id || "", status: c.status },
    queue: cases.map((x) => ({ id: x.id, key: x.key, title: x.title, status: x.status })),
    queueOver: {},
    uploadError: null,
    skipReasons: SKIP_REASONS,
    skip: { reason: "", blockingDefect: "" },
    builds: buildOpts(builds)
  };
  const q = params.cc ? cases.findIndex((x) => x.id === params.cc) : cases.findIndex((x) => x.status === "untested");
  if (params.cc && q < 0) throw new Error(`Cycle case ${params.cc} is not in this cycle.`);
  if (q < 0) return { state: "complete", data };
  const cc = cases[q];
  const [v, attempts, saved] = await Promise.all([
    get(path("cases", cc.case_id, "versions", String(cc.case_version)), { rich: "both" }),
    cc.last_result_at ? all(path("cycle-cases", cc.id, "results")) : [],
    params.ui === "submitted" && params.done ? all(path("cycle-cases", params.done, "results")) : null
  ]);
  const pre = plain(v.preconditions);
  data.current = { q, step: 0, res: [] };
  const last = attempts[attempts.length - 1];
  data.case = {
    id: cc.id, key: cc.key, title: cc.title, pin: cc.case_version, newer: cc.current_version > cc.case_version ? cc.current_version : 0,
    attempt: attempts.length + 1, preconditions: pre, preShort: pre.length > 40 ? pre.slice(0, 40) + "…" : pre,
    /* the build under test: the last attempt's, else the newest recorded for the product, else none */
    build: (last && last.build) || (builds[0] ? builds[0].build : ""),
    steps: v.steps.map((s) => ({ id: s.id, action: html(s.action.doc), expected: html(s.expected.doc) }))
  };
  data.failure = { actual: "", files: [], defectUrl: "", defectKey: "" };
  data.previous = last ? previous(last) : null;
  if (saved && saved.length) {
    data.saved = savedOf(cases.find((x) => x.id === params.done) || { key: "" }, saved);
    return { state: "submitted", data };
  }
  if (UI.includes(params.ui)) return { state: params.ui, data };
  return { state: attempts.length ? "retest" : "in-progress", data };
}

/* The view's writes; each resolves to what the server returns. */
export const actions = {
  /* body: a ResultCreate { status, comment, duration_ms, steps, defects, skip_reason, build } -> ResultOut (the
     next attempt) */
  submit: (cycleCaseId, body, ctx) => post(org(ctx.org.id, "cycle-cases", cycleCaseId, "results"), body),
  /* file: { filename, mime, content_base64 } -> AttachmentOut (a 413 when it's too large) */
  attach: (productKey, file, ctx) => post(org(ctx.org.id, "products", productKey, "attachments", "base64"), file)
};
