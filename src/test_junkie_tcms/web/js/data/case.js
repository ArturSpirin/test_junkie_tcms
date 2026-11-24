/* Case adapter (docs/app-api-contract.md §5): cases_get (rich text as both the stored doc, drawn as HTML, and
   its Markdown), the current version's provenance (cases_version_get, actors_list, members_list for "on behalf
   of"), where the case sits
   (features_list, releases_list, plans_list, cases_cycles), tags_list, and cases_markdown_get for the Markdown
   view. Writes: cases_update with If-Match (and cases_move for a new feature), cases_markdown_put with If-Match,
   cases_create. A failed write throws the ApiError; the view shows it raw.
   URL: ?view=case&id=<key or id>#<ui>; ui is "markdown", "saved" or "new-case" (with &feature=<id>). */
import { all, get, org, patch, post, put, rawError } from "../api.js";
import { flatten } from "./map.js";

/* the text a view shows for a failed write, word for word */
export const raw = rawError;

/* the step a refused save names, { i, field }, or null: a request-validation 422 points at it by `loc`
   (["body", "steps", 2, "expected", ...]), a rich-text 422 by its detail ("steps[2].expected: ...") */
export function stepError(e) {
  if (!e || e.status !== 422) return null;
  const b = e.body || {};
  const loc = (b.errors || []).map((x) => x.loc || []).find((l) => Number.isInteger(l[l.indexOf("steps") + 1]) && l.includes("steps"));
  if (loc) { const at = loc.indexOf("steps"); return { i: loc[at + 1], field: loc[at + 2] === "action" ? "action" : "expected" }; }
  const m = /^steps\[(\d+)\]\.(action|expected)\b/.exec(b.detail || "");
  return m ? { i: Number(m[1]), field: m[2] } : null;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/* ---------- a stored rich-text doc (ProseMirror JSON) as the HTML the editor shows ---------- */
const MARK = { bold: "b", italic: "i", strike: "s", code: "code" };
function inline(n) {
  if (n.type === "hardBreak") return "<br>";
  if (n.type === "image") return `<span class="img" data-src="${esc(n.attrs && n.attrs.src)}">${esc((n.attrs && n.attrs.alt) || "image")}</span>`;
  let s = esc(n.text);
  // marks come outermost first: wrap from the innermost out
  for (const m of [...(n.marks || [])].reverse()) {
    s = m.type === "link" ? `<a href="${esc(m.attrs.href)}">${s}</a>` : MARK[m.type] ? `<${MARK[m.type]}>${s}</${MARK[m.type]}>` : s;
  }
  return s;
}
const kids = (n) => (n.content || []).map(block).join("");
/* a list item holding one paragraph shows it bare, as a tight list */
const item = (n) => (n.content && n.content.length === 1 && n.content[0].type === "paragraph" ? (n.content[0].content || []).map(inline).join("") : kids(n));
function block(n) {
  switch (n.type) {
    case "paragraph": return `<p>${(n.content || []).map(inline).join("")}</p>`;
    case "heading": return `<h${n.attrs.level}>${(n.content || []).map(inline).join("")}</h${n.attrs.level}>`;
    case "bulletList": return `<ul>${(n.content || []).map((li) => `<li>${item(li)}</li>`).join("")}</ul>`;
    case "orderedList": return `<ol${n.attrs && n.attrs.start !== 1 ? ` start="${n.attrs.start}"` : ""}>${(n.content || []).map((li) => `<li>${item(li)}</li>`).join("")}</ol>`;
    case "taskList": return `<ul class="cl">${(n.content || []).map((li) => `<li${li.attrs && li.attrs.checked ? ' class="done"' : ""}>${item(li)}</li>`).join("")}</ul>`;
    case "codeBlock": return `<pre><code>${esc((n.content || []).map((t) => t.text).join(""))}</code></pre>`;
    case "blockquote": return `<blockquote>${kids(n)}</blockquote>`;
    case "table": return `<table>${(n.content || []).map((tr) => `<tr>${(tr.content || []).map((c) => { const t = c.type === "tableHeader" ? "th" : "td"; return `<${t}>${item(c)}</${t}>`; }).join("")}</tr>`).join("")}</table>`;
    case "horizontalRule": return "<hr>";
    default: return inline(n);
  }
}
/* a doc of one paragraph shows bare, the way the step cells hold one line */
export function html(doc) {
  const c = (doc && doc.content) || [];
  if (c.length === 1 && c[0].type === "paragraph") return (c[0].content || []).map(inline).join("");
  return c.map(block).join("");
}

/* rich=both gives { markdown, doc } per rich field */
const rich = (v) => ({ html: html(v.doc), md: v.markdown });

/* "Thu Nov 12, 3:14 PM" in the browser's zone */
const at = (iso) => new Date(iso).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).replace(/^(\w+),/, "$1");

/* the case's feature and its parents, nearest first */
function lineage(features, id) {
  const by = Object.fromEntries(features.map((f) => [f.id, f]));
  const out = [];
  for (let f = by[id]; f; f = by[f.parent_id]) out.push(f.id);
  return out;
}

async function product(path, p) {
  const [tree, tags, releases, plans] = await Promise.all([
    get(path("products", p.key, "features")), all(path("products", p.key, "tags")),
    all(path("products", p.key, "releases")), all(path("products", p.key, "plans"))
  ]);
  const features = flatten(tree.items);
  return {
    features, releases, plans,
    folders: features.map((f) => ({ v: f.id, label: f.path.split(" › ").join(" / "), name: f.name, path: f.path, cases: f.total_case_count })),
    tags: tags.map((t) => ({ v: t.name, cases: t.case_count }))
  };
}

const BASE = { order: [], lift: null, over: null, invalidStep: null, invalidField: "expected", error: "", currentVersion: null };

/* params: the URL's query (id: a case key or id; feature: a new case's feature) and ui, the hash's UI state. */
export async function load(params, ctx) {
  const p = ctx.product;
  if (!p) throw new Error("This org has no products yet. Add a product, then its cases.");
  const path = (...rest) => org(ctx.org.id, ...rest);
  const ro = ["viewer", "tester"].includes(ctx.user.role);
  if (!params.id) {
    const pr = await product(path, p);
    if (!pr.features.length) throw new Error(`${p.key} has no features yet. Every case sits under a feature: add one on the feature tree first.`);
    const feature = pr.features.some((f) => f.id === params.feature) ? params.feature : pr.features[0].id;
    const up = lineage(pr.features, feature);
    const ver = Object.fromEntries(pr.releases.map((r) => [r.id, r.version]));
    const pickedUpBy = pr.plans.filter((pl) => pl.entries.some((e) => up.includes(e.feature_id)))
      .map((pl) => ({ name: pl.name, ver: pl.release_id ? ver[pl.release_id] : "any version" }));
    return { state: "new-case", data: { ...BASE, folders: pr.folders, tags: pr.tags, case: {
      id: "", key: "", title: "", version: 0, feature, status: "draft", priority: "medium", type: "functional", automation: "manual",
      autoRef: "", tags: [], links: [], desc: "", pre: "", steps: [{ id: "", action: "", expected: "" }], changeNote: "", pickedUpBy
    } } };
  }
  const c = await get(path("cases", params.id), { rich: "both" });
  // the case's own product (a link may open a case of another product than the shell's)
  const [pr, v, actors, cycles, md] = await Promise.all([
    product(path, ctx.products.find((x) => x.id === c.product_id) || p),
    get(path("cases", c.id, "versions", String(c.current_version))),
    get(path("actors")),
    get(path("cases", c.id, "cycles")),
    params.ui === "markdown" && !ro ? get(path("cases", c.id, "markdown")) : null
  ]);
  const up = lineage(pr.features, c.feature_id);
  const who = actors.actors.find((a) => a.id === v.created_by_actor_id);
  // "on behalf of" names a user: the member with that user id
  const behalf = v.on_behalf_of_user_id ? (await all(path("members"))).find((m) => m.user_id === v.on_behalf_of_user_id) : null;
  const open = cycles.filter((x) => x.cycle_status !== "closed");
  const desc = rich(c.description), pre = rich(c.preconditions);
  const steps = c.steps.map((s) => ({ id: s.id, ...Object.fromEntries(["action", "expected"].map((k) => [k, html(s[k].doc)])) }));
  const data = { ...BASE, folders: pr.folders, tags: pr.tags, case: {
    id: c.id, key: c.key, title: c.title, version: md ? md.version : c.current_version,
    feature: c.feature_id, status: c.status, priority: c.priority, type: c.type, automation: c.automation,
    autoRef: c.automation_ref || "", tags: c.tags, links: c.links.map((l) => ({ key: l.key || "", url: l.url })),
    desc: desc.html, pre: pre.html, steps,
    /* the stored Markdown of each rich field: what a save sends back for a field the user left alone */
    src: { desc: desc.md, pre: pre.md, steps: Object.fromEntries(c.steps.map((s) => [s.id, { action: s.action.markdown, expected: s.expected.markdown }])) },
    md: md ? md.markdown : "",
    versions: pr.releases.filter((r) => r.feature_ids.some((f) => up.includes(f))).map((r) => ({ ver: r.version, status: r.status, href: { view: "releases", id: r.id } })),
    plans: pr.plans.flatMap((pl) => {
      const via = pl.entries.some((e) => e.case_id === c.id) ? "case" : pl.entries.some((e) => up.includes(e.feature_id)) ? "feature" : null;
      return via ? [{ name: pl.name, via, href: { view: "plans", id: pl.id } }] : [];
    }),
    cycles: cycles.map((x) => ({ name: x.name, pin: x.case_version, href: { view: "cycles", id: x.cycle_id } })),
    current: {
      by: { kind: who ? who.kind : "user", name: who ? who.name : v.created_by_actor_id },
      onBehalf: behalf ? behalf.name : v.on_behalf_of_user_id || "", via: v.via || "", at: at(v.created_at),
      openCycles: open.length, pins: [...new Set(open.map((x) => x.case_version))].sort((a, b) => a - b)
    },
    changeNote: ""
  } };
  if (ro) return { state: "viewer", data };
  if (md) return { state: "markdown", data };
  // after a save the page loads again: the case is now at the version just saved
  if (params.ui === "saved") return { state: "saved", data: { ...data, savedAs: c.current_version } };
  return { state: "default", data };
}

/* the markdown each rich field sends: an edit (a string) as typed, an untouched field (null) as stored */
const md = (s) => ({ markdown: s });
function stepsBody(c, steps) {
  const same = steps.length === c.steps.length && steps.every((s, i) => s.id === c.steps[i].id && s.action === null && s.expected === null);
  if (same) return undefined;
  return steps.map((s) => {
    const was = c.src.steps[s.id] || { action: "", expected: "" };
    return { id: s.id || undefined, action: md(s.action ?? was.action), expected: md(s.expected ?? was.expected) };
  });
}
const fields = (f) => ({
  status: f.status, priority: f.priority, type: f.type, automation: f.automation,
  automation_ref: f.autoRef || null, tags: f.tags, links: f.links.map((l) => ({ url: l.url, key: l.key || null })),
  change_note: f.changeNote || null
});

/* The view's writes; each resolves to the server's CaseOut.
   edit: { title, desc, pre (Markdown, or null when untouched), steps: [{ id ("" for a new one), action, expected }],
   feature, status, priority, type, automation, autoRef, tags, links: [{ url, key }], changeNote }. */
export const actions = {
  /* cases_update with If-Match version (the case as loaded, or the current one after a 409), then cases_move
     when the feature changed */
  async save(c, edit, ctx, version = c.version) {
    const path = (...rest) => org(ctx.org.id, ...rest);
    let out = await patch(path("cases", c.id), {
      title: edit.title, ...fields(edit),
      description: edit.desc === null ? undefined : md(edit.desc),
      preconditions: edit.pre === null ? undefined : md(edit.pre),
      steps: stepsBody(c, edit.steps)
    }, { ifMatch: version });
    if (edit.feature && edit.feature !== c.feature) out = await post(path("cases", c.id, "move"), { feature_id: edit.feature });
    return out;
  },
  /* cases_markdown_put: the edited file as the next version */
  saveMarkdown(c, markdown, changeNote, ctx, version = c.version) {
    return put(org(ctx.org.id, "cases", c.id, "markdown"), { markdown, change_note: changeNote || null }, { ifMatch: version });
  },
  /* cases_create in the current product */
  create(edit, ctx) {
    const steps = edit.steps.filter((s) => s.action || s.expected).map((s) => ({ action: md(s.action || ""), expected: md(s.expected || "") }));
    return post(org(ctx.org.id, "products", ctx.product.key, "cases"), {
      feature_id: edit.feature, title: edit.title, ...fields(edit),
      description: edit.desc ? md(edit.desc) : undefined, preconditions: edit.pre ? md(edit.pre) : undefined, steps
    });
  }
};
