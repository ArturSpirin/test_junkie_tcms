/* Features and cases adapter (docs/app-api-contract.md §3): features_list (the tree, its counts and last
   editor; ?q= for the name search), cases_list (the selected feature's cases with the filters, sort and q the
   server applies; product-wide for the search's case hits), tags_list, reports_feature (latest result per
   case in the current version), releases_list, plans_list and cycles_list for where the feature is used, and
   products_list with archived products for the product switcher. Writes: features_create, features_update,
   features_move and cases_move. Maps the API onto the shapes views/tree.js renders. */
import { all, get, org, page, patch, post } from "../api.js";
import { day, flatten, markCls, results } from "./map.js";

const CASES_PAGE = 100;
const UI_STATES = ["new-feature", "move", "desc-edit", "desc-saved", "desc-agent", "nav-open", "search-cleared"];
/* roles that can't change the catalog or move cases: the tree is read only for them */
const READ_ONLY = ["viewer", "tester"];
/* a filter param holds a comma-separated list */
const list = (v) => String(v || "").split(",").map((s) => s.trim()).filter(Boolean);
const EDITED = ["7d", "me", "agent"];
const REF = ["ref", "noref"];

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
const at = (ctx) => (...rest) => org(ctx.org.id, ...rest);
const stamp = (iso) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/* A rich text doc (rich=doc, the ProseMirror node set of richtext/schema.py) as HTML; every text escaped. */
const MARK = { bold: ["<b>", "</b>"], italic: ["<em>", "</em>"], strike: ["<s>", "</s>"], code: ["<code>", "</code>"] };
function html(node) {
  if (!node) return "";
  const kids = () => (node.content || []).map(html).join("");
  const a = node.attrs || {};
  switch (node.type) {
    case "doc": return kids();
    case "text": {
      let s = esc(node.text);
      for (const m of [...(node.marks || [])].reverse()) {
        s = m.type === "link" ? `<a href="${esc(m.attrs.href)}" rel="noopener">${s}</a>` : MARK[m.type] ? MARK[m.type][0] + s + MARK[m.type][1] : s;
      }
      return s;
    }
    case "paragraph": return `<p>${kids()}</p>`;
    case "heading": return `<h${a.level || 1}>${kids()}</h${a.level || 1}>`;
    case "bulletList": return `<ul>${kids()}</ul>`;
    case "orderedList": return `<ol${a.start && a.start !== 1 ? ` start="${Number(a.start)}"` : ""}>${kids()}</ol>`;
    case "taskList": return `<ul class="cl">${kids()}</ul>`;
    case "listItem": return `<li>${kids()}</li>`;
    case "taskItem": return `<li${a.checked ? ' class="done"' : ""}>${kids()}</li>`;
    case "codeBlock": return `<pre><code>${(node.content || []).map((t) => esc(t.text)).join("")}</code></pre>`;
    case "blockquote": return `<blockquote>${kids()}</blockquote>`;
    case "table": return `<table>${kids()}</table>`;
    case "tableRow": return `<tr>${kids()}</tr>`;
    case "tableHeader": return `<th>${kids()}</th>`;
    case "tableCell": return `<td>${kids()}</td>`;
    case "horizontalRule": return "<hr>";
    case "hardBreak": return "<br>";
    case "image": return `<span class="img">${esc(a.alt || "image")}</span>`;
    default: return kids();
  }
}

/* the product the view is about: the context's (?product=) */
function productOf(ctx) {
  const p = ctx.product;
  if (!p) throw new Error("This org has no products yet.");
  return { id: p.id, key: p.key, name: p.name };
}

/* a CaseOut as a tree row (t "c") */
const caseNode = (c) => ({
  id: c.id, t: "c", key: c.key, title: c.title, ver: c.current_version, life: c.status, auto: c.automation,
  pri: c.priority, tags: c.tags, last: c.last_result || "untested", pos: c.position, fid: c.feature_id
});

/* The tree model from FeatureNodes: features keep their sub-features first, then the cases placed on them;
   `more` counts a feature's own cases that are not loaded. keep (a Set, for a search) prunes to those ids and
   shows only the matches (no `more`); open (a Set) opens those features. */
function model(nodes, cases, keep, open) {
  const by = {};
  for (const c of cases) (by[c.fid] = by[c.fid] || []).push(c);
  const walk = (ns) => ns.filter((n) => !keep || keep.has(n.id)).map((n) => {
    const mine = by[n.id] || [];
    const subs = walk(n.children || []);
    return { id: n.id, t: "f", name: n.name, kids: [...subs, ...mine], more: keep ? 0 : Math.max(0, n.case_count - mine.length), open: open.has(n.id) && (subs.length + mine.length > 0), pos: n.position, parent: n.parent_id || null };
  });
  return walk(nodes);
}

/* the filters in the URL: tag, status (with the Edited options), result, automation (with the ref options),
   priority; null when none is set */
function filtersOf(params) {
  const f = { tag: list(params.tag), status: list(params.status), result: list(params.result), automation: list(params.automation), priority: list(params.priority) };
  return Object.values(f).some((v) => v.length) ? f : null;
}

/* the cases_list query for the filters, the sort and q: the server filters and sorts. me: the signed-in
   actor's id, for "Edited by me" */
function caseQuery(f, sort, q, me) {
  const out = { sort: sort || "manual", q: q || undefined };
  if (!f) return out;
  const life = f.status.filter((s) => !EDITED.includes(s));
  const auto = f.automation.filter((s) => !REF.includes(s));
  const ref = f.automation.filter((s) => REF.includes(s));
  Object.assign(out, { tag: f.tag, status: life, result: f.result, automation: auto, priority: f.priority });
  if (f.status.includes("7d")) out.updated_since = new Date(Date.now() - 7 * 864e5).toISOString();
  if (f.status.includes("me") && me) out.edited_by = me;
  if (f.status.includes("agent")) out.edited_by_kind = "agent";
  if (ref.length === 1) out.has_ref = ref[0] === "ref";
  return out;
}

/* everything the feature card shows: coverage, latest results, and the versions, plans and cycles using it */
async function featureCard(path, ctx, product, f, parentName, cases) {
  const count = (query) => page(path("products", product.key, "cases"), { feature: f.id, ...query, limit: 1 }).then((p) => p.total);
  const rel = ctx.version;
  const [ready, draft, automated, toAutomate, report, releases, plans, cycles] = await Promise.all([
    count({ status: "ready" }), count({ status: "draft" }), count({ automation: "automated" }), count({ automation: "to_automate" }),
    get(path("features", f.id, "report"), rel ? { release: rel.id, limit: 1 } : { limit: 1 }),
    all(path("products", product.key, "releases")),
    all(path("products", product.key, "plans")),
    all(path("products", product.key, "cycles"))
  ]);
  const c = report.counts;
  const total = f.total_case_count;
  const keys = Object.fromEntries(cases.map((x) => [x.id, x.key]));
  const by = f.updated_by;
  const people = ctx.people || {};
  return {
    id: f.id, name: f.name, parent: parentName,
    owner: f.owner_actor_id && people[f.owner_actor_id] ? people[f.owner_actor_id][0] : "",
    desc: html(f.description),
    edited: by ? { by: by.id, when: stamp(f.updated_at) } : null,
    /* a feature's last edit carries only its actor: no via or on-behalf-of (those are on case versions) */
    agentEdit: by && by.kind === "agent" ? { agent: by.name, when: stamp(f.updated_at) } : null,
    stats: {
      cases: total, ready, draft, automated, toAutomate, automatedPct: total ? Math.round((automated / total) * 100) : 0,
      ran: (c.total || 0) - (c.untested || 0), ranIn: rel ? rel.ver : "the last 30 days"
    },
    latest: results(c),
    versions: releases.filter((r) => r.feature_ids.includes(f.id)).map((r) => ({ id: r.id, ver: r.version, status: r.status })),
    plans: plans.map((p) => {
      if (p.entries.some((e) => e.feature_id === f.id)) return { id: p.id, name: p.name, scope: "whole feature" };
      const mine = p.entries.filter((e) => e.case_id && keys[e.case_id]).map((e) => keys[e.case_id]);
      return mine.length ? { id: p.id, name: p.name, scope: mine.length === 1 ? `${mine[0]} only` : `${mine.length} cases` } : null;
    }).filter(Boolean),
    cycles: cycles.filter((cy) => cy.feature_id === f.id).map((cy) => ({
      id: cy.id, name: cy.name, status: cy.status, pinned: Object.values(cy.counts || {}).reduce((n, v) => n + v, 0)
    }))
  };
}

/* the move dialog's destinations: the product root and every feature, the moved one's subtree disabled */
function dests(flat, product, src) {
  const inside = new Set();
  for (const f of flat) if (f.id === src.id || inside.has(f.parent_id)) inside.add(f.id);
  const cur = src.parent_id || "root";
  return [
    { v: "root", label: `${product.name} (top level)`, hint: cur === "root" ? "Current parent" : "Product root", root: true },
    ...flat.map((f) => ({
      v: f.id, label: f.path.replace(/ › /g, " / "),
      hint: inside.has(f.id) ? "A feature can't go inside itself" : f.id === cur ? "Current parent" : f.total_case_count ? `${f.total_case_count} cases` : "Empty",
      dis: inside.has(f.id)
    }))
  ];
}

/* params: the URL's query (product, feature, q, the filters, sort; moved, from and pos after a drop) and ui,
   the hash's UI state ("new-feature", "move", "desc-edit", ...). */
export async function load(params, ctx) {
  const path = at(ctx);
  const product = productOf(ctx);
  const q = (params.q || "").trim();
  const filter = filtersOf(params);
  const sort = params.sort || "manual";
  const [tree, every, tags] = await Promise.all([
    get(path("products", product.key, "features"), { rich: "doc" }),
    all(path("products"), { include_archived: true }),
    page(path("products", product.key, "tags"))
  ]);
  const flat = flatten(tree.items);
  const byId = Object.fromEntries(flat.map((f) => [f.id, f]));
  const sel = byId[params.feature] || flat.find((f) => f.case_count) || flat[0] || null;
  const data = {
    product, picked: product.key, readOnly: READ_ONLY.includes(ctx.user.role),
    products: every.filter((p) => !p.archived_at).map((p) => ({ key: p.key, name: p.name, short: `${p.key} · ${p.name}`, markCls: markCls(p.key), cases: p.case_count, features: p.feature_count })),
    archived: every.filter((p) => p.archived_at).map((p) => ({ key: p.key, name: p.name, archivedOn: day(p.archived_at) })),
    tags: tags.items.map((t) => ({ tag: t.name, cases: t.case_count })),
    empty: !flat.length, tree: [], sel: sel ? sel.id : null, q, filter, sort, cases: [], casesTotal: 0, feature: null,
    newUnder: null, newName: ""
  };
  if (params.ui === "new-feature" && !data.readOnly) data.newUnder = sel ? sel.id : "root";
  if (!sel) return { state: data.newUnder ? "new-feature" : "empty-product", data };

  const casesPath = path("products", product.key, "cases");
  const me = filter && filter.status.includes("me") ? (await get("/api/v1/me")).actor_id : null;
  const [mine, hits, names] = await Promise.all([
    page(casesPath, { feature: sel.id, ...caseQuery(filter, sort, q, me), limit: CASES_PAGE }),
    q ? page(casesPath, { ...caseQuery(filter, sort, q, me), limit: CASES_PAGE }) : null,
    q ? get(path("products", product.key, "features"), { q }) : null
  ]);
  data.cases = mine.items.map(caseNode);
  data.casesTotal = mine.total;
  const ancestors = (id) => { const out = []; for (let f = byId[id]; f; f = byId[f.parent_id]) out.push(f.id); return out; };
  const parentName = sel.parent_id ? byId[sel.parent_id].name : product.name;
  if (q) {
    /* the server's matches: the features named like q (with their parents) and the cases it found */
    const placed = hits.items.map(caseNode);
    const keep = new Set([...flatten(names.items).map((f) => f.id), ...placed.flatMap((c) => ancestors(c.fid))]);
    const open = new Set([...keep].filter((id) => placed.some((c) => ancestors(c.fid).includes(id)) || flat.some((f) => f.parent_id === id && keep.has(f.id))));
    data.tree = model(tree.items, placed, keep, open);
    data.hits = hits.total;
    data.feats = flatten(names.items).filter((f) => f.name.toLowerCase().includes(q.toLowerCase())).length;
  } else {
    const open = new Set([...flat.filter((f) => !f.parent_id).map((f) => f.id), ...ancestors(sel.id)]);
    data.tree = model(tree.items, data.cases, null, open);
  }
  data.feature = await featureCard(path, ctx, product, sel, parentName, data.cases);

  if (params.ui === "move" && !data.readOnly) {
    data.move = { src: sel.id, dest: sel.parent_id || "root", from: sel.parent_id || "", pos: sel.position, dests: dests(flat, product, sel) };
    return { state: "move", data };
  }
  if (params.moved && params.ui === "dropped") {
    /* after a move: where the moved feature or case was (from: its parent or feature, "" for the top level;
       pos: its place there), so Undo can put it back */
    data.moved = params.moved;
    data.undo = { kind: byId[params.moved] ? "f" : "c", from: params.from || "", pos: Number(params.pos) || 0 };
    const found = byId[params.moved] || data.cases.some((c) => c.id === params.moved);
    if (found) return { state: "dropped", data };
  }
  if (q) return { state: data.tree.length ? "search" : "search-empty", data };
  if (data.readOnly) return { state: "read-only", data };
  if (params.ui === "desc-agent" && !data.feature.agentEdit) return { state: "default", data };
  if (UI_STATES.includes(params.ui)) return { state: params.ui, data };
  if (filter) return { state: "filters", data };
  return { state: "default", data };
}

/* The view's writes; each resolves to the FeatureOut or CaseOut the server returns. */
export const actions = {
  /* parent: a feature id, or null for the top level */
  createFeature: (name, parent, ctx) => post(at(ctx)("products", ctx.product.key, "features"), { name, parent_id: parent || null }),
  /* change: FeatureUpdate's fields, e.g. { description: { markdown } } */
  updateFeature: (id, change, ctx) => patch(at(ctx)("features", id), change),
  /* parent: a feature id or null (the top level); position: the index among its sub-features */
  moveFeature: (id, parent, position, ctx) => post(at(ctx)("features", id, "move"), { parent_id: parent || null, position }),
  /* position: the index among the feature's cases; none appends */
  moveCase: (id, feature, position, ctx) => post(at(ctx)("cases", id, "move"), position === undefined || position === null ? { feature_id: feature } : { feature_id: feature, position })
};
