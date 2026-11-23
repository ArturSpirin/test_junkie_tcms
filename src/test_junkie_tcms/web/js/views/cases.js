/* Test cases: every case in a product across features, with search, filters and sort. The data is
   data/cases.js: the server searches, filters, sorts and pages (the view never does), and the filters live in
   the URL, so a filter change loads the list again. */
import { I, st, ver, dd, esc, psearch, hl, crumbs, footBar } from "../ui.js";
import { href } from "../shell.js";
import { PAGE, paramsOf } from "../data/cases.js";

const PRI_COL = { critical: "var(--fail)", high: "var(--blocked)", medium: "var(--retest)", low: "var(--faint)" };
const AUTO_IC = { manual: I.person, automated: I.bolt, to_automate: I.spark };
const filtered = (f) => !!(f.feature.length || f.status.length || f.result.length || f.automation.length || f.priority.length);
/* the list's URL params: its search, filters and sort (rows shown start again at one page) */
const here = (d, over = {}) => ({ q: d.q || null, sort: d.sort, ...paramsOf(d.filter), ...over });
const productCrumb = (d) => [esc(`${d.product.key} · ${d.product.name}`), href("products", { id: d.product.key })];

const head = (d) => `${crumbs([productCrumb(d), ["Test cases"]])}<div class="ph"><div class="ttl"><span class="eyebrow">Features and cases · ${esc(d.product.key)}</span><h1>Test cases</h1></div><div class="actions"><a class="btn hide-n" href="${href("tree")}">${I.tree}View as feature tree</a><a class="btn primary" href="${href("case", {}, "new-case")}">${I.plus}New case</a></div></div>`;

function filters(d) {
  const f = d.filter;
  const v = filtered(f);
  /* cases_list filters by one feature (with its sub-features) */
  const featOpts = [{ v: "", label: "Any feature", icon: I.folder }, "-", { group: `Features in ${d.product.key}` }, ...d.features.map((x) => ({ v: x.id, label: x.path, short: x.short, hint: `${x.cases} cases`, icon: I.folder }))];
  const lifeOpts = [{ group: "Case status" },
    { v: "draft", label: "draft", hint: "Work in progress", dot: "var(--faint)" },
    { v: "ready", label: "ready", hint: "Can be added to cycles", dot: "var(--pass)" },
    { v: "deprecated", label: "deprecated", hint: "Kept for history", dot: "var(--untested)" }];
  const resultOpts = [{ group: "Last Test Junkie result" }, ...["success", "fail", "error", "ignore", "skip", "cancel"].map((r) => ({ v: r, label: r, dot: `var(--st-${r})` })), "-", { v: "untested", label: "untested", hint: "No result in any cycle", dot: "var(--st-untested)" }];
  const autoOpts = [{ group: "Automation" }, ...Object.keys(AUTO_IC).map((a) => ({ v: a, label: a, icon: AUTO_IC[a] }))];
  const priOpts = [{ group: "Priority" }, ...Object.keys(PRI_COL).map((p) => ({ v: p, label: p, dot: PRI_COL[p] }))];
  const sortOpts = [{ group: "Sort cases by" }, { v: "key", label: "Key", icon: I.tag }, { v: "title", label: "Title A to Z", icon: I.doc }, { v: "updated", label: "Last updated", icon: I.clock }, { v: "result", label: "Last result, fail first", icon: I.okcirc }, { v: "priority", label: "Priority, critical first", icon: I.flag }];
  return `<div class="filters">
    ${dd({ value: f.feature[0], options: featOpts, search: "Find a feature", pre: "Feature", placeholder: "Any", cls: "sm", w: "200px", label: "Feature", open: d.open === "feature", name: "feature" })}
    ${dd({ multi: true, value: f.status, options: lifeOpts, pre: "Status", placeholder: "Any", cls: "sm", w: "184px", label: "Status", name: "status" })}
    ${dd({ multi: true, value: f.result, options: resultOpts, pre: "Last result", placeholder: "Any", cls: "sm", w: "180px", label: "Last result", name: "result" })}
    ${dd({ multi: true, value: f.automation, options: autoOpts, pre: "Automation", placeholder: "Any", cls: "sm hide-n", w: "190px", label: "Automation", name: "automation" })}
    ${dd({ multi: true, value: f.priority, options: priOpts, pre: "Priority", placeholder: "Any", cls: "sm hide-n", w: "150px", label: "Priority", name: "priority" })}
    ${v ? `<a class="btn ghost sm" href="${href("cases", { q: d.q || null, sort: d.sort })}">Clear filters</a>` : ""}<span class="sp"></span>
    ${dd({ value: d.sort, options: sortOpts, pre: "Sort", cls: "sm ghost", w: "196px", label: "Sort", name: "sort" })}
  </div>`;
}

function table(list, q) {
  const tags = (c) => c.tags.map((t) => "#" + esc(t)).join(" ");
  const pri = (p) => `<span class="pri"><span class="dot" style="--c:${PRI_COL[p]}"></span>${p}</span>`;
  const to = (c) => href("case", { id: c.key });
  const rowsH = list.map((c) => `<tr class="${c.status === "deprecated" ? "dim" : ""}" data-href="${to(c)}">
    <td class="key">${hl(esc(c.key), q)}</td>
    <td class="tt"><a href="${to(c)}" class="ell" title="${esc(c.title)}">${hl(esc(c.title), q)}</a><div class="fpath ell">${I.folder} ${esc(c.feature)}${c.tags.length ? " · " + tags(c) : ""}</div></td>
    <td>${ver(c.version)}</td><td><span class="pill ${c.status}">${c.status}</span></td><td>${st(c.result)}</td>
    <td class="hide-m"><span class="auto">${AUTO_IC[c.automation]}${c.automation}</span></td><td class="hide-m">${pri(c.priority)}</td><td class="hide-m faint" style="font-size:12px;white-space:nowrap">${esc(c.updated)}</td></tr>`).join("");
  const mrows = list.map((c) => `<a class="it" href="${to(c)}"><div class="row"><span class="key">${hl(esc(c.key), q)}</span>${ver(c.version)}<span class="pill ${c.status}">${c.status}</span>${st(c.result)}</div><b style="font-weight:500">${hl(esc(c.title), q)}</b><span class="faint" style="font-size:12px">${esc(c.feature)}</span><span class="auto">${AUTO_IC[c.automation]}${c.automation} · ${c.priority}</span></a>`).join("");
  return `<div class="tbl-wrap mswap"><table class="t"><thead><tr><th>Key</th><th>Title and feature</th><th>Version</th><th>Status</th><th>Last result</th><th class="hide-m">Automation</th><th class="hide-m">Priority</th><th class="hide-m">Updated</th></tr></thead><tbody>${rowsH}</tbody></table></div><div class="mlist">${mrows}</div>`;
}

const cleared = (d) => href("cases", here(d, { q: null }), "search-cleared");
const noHits = (d, q) => q
  ? `<div class="empty"><div class="ill">${I.search}</div><h3>No cases match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:440px">Search looks at case keys, titles, steps and tags in ${esc(d.product.key)}. Try a key such as “${esc(d.product.key)}-101” or a word from a title.</p><a class="btn" href="${cleared(d)}">Clear search</a></div>`
  : `<div class="empty"><div class="ill">${I.search}</div><h3>No cases match these filters</h3><p class="muted" style="margin:0 auto 14px;max-width:440px">Try fewer filters.</p><a class="btn" href="${href("cases", { sort: d.sort })}">Clear filters</a></div>`;

/* d.cases is the page the server matched for d.q and d.filter, d.matched counts every match, d.total every case */
function list(d) {
  const q = d.q;
  const v = filtered(d.filter);
  const P = esc(d.product.key);
  const rows = d.cases;
  const cnt = d.matched + (d.matched === 1 ? " case" : " cases");
  const more = rows.length < d.matched ? footBar(`<a class="btn sm" href="${href("cases", here(d, { shown: d.shown + PAGE }))}">Load ${Math.min(PAGE, d.matched - rows.length)} more</a>`, `${rows.length} of ${d.matched} cases`) : "";
  return head(d) + `<div class="sub" style="margin-bottom:16px">Every test case in ${P}, across all features. Pick a case to open it in the editor.</div>` +
    psearch({ q, ph: "Search cases by key, title, step or tag", cnt, clear: cleared(d) }) + filters(d) +
    `<div class="card"><div class="hd"><h2>Cases in ${P}</h2><span class="r faint" style="font-size:12px">${q || v ? `${d.matched} of ${d.total}` : `showing ${rows.length} of ${d.total}`}</span></div>${rows.length ? table(rows, q) : noHits(d, q)}${rows.length ? more : ""}</div>`;
}

const empty = (d) => {
  const P = esc(d.product.key);
  return `${crumbs([productCrumb(d), ["Test cases"]])}<div class="ph"><div class="ttl"><span class="eyebrow">Features and cases · ${P}</span><h1>Test cases</h1></div><div class="actions"><a class="btn primary" href="${href("case", {}, "new-case")}">${I.plus}New case</a></div></div>
  <div class="card"><div class="hd"><h2>Cases in ${P}</h2></div><div class="empty"><div class="ill">${I.doc}</div><h3>No test cases in ${P} yet</h3><p class="muted" style="margin:0 auto 14px;max-width:460px">Write a case by hand, import a CSV, or let an agent draft cases through MCP. Cases go under a feature.</p><a class="btn" href="${href("tree")}">${I.tree}Add features first</a> <a class="btn primary" href="${href("case", {}, "new-case")}">${I.plus}New case</a></div></div>`;
};

/* the real controls: Enter in the search box, the filter and sort menus (each change loads the list from the
   server; a multi-choice menu applies when it closes), and a click anywhere on a row opens the case */
let cur = null;
let pending = null;
const picked = (dd) => [...dd.querySelectorAll(".dd-o.sel")].map((o) => o.dataset.v).filter(Boolean).join(",") || null;
const go = (over) => { location.href = href("cases", here(cur, over)); };
function after(main, state, d) {
  cur = d;
  pending = null;
  const box = main.querySelector(".psearch input");
  if (box) box.addEventListener("keydown", (e) => {
    if (e.key === "Enter") go({ q: box.value.trim() || null });
  });
  if (main._cases) return;
  main._cases = true;
  main.addEventListener("click", (e) => { const tr = e.target.closest("tr[data-href]"); if (tr && !e.target.closest("a")) location.href = tr.dataset.href; });
  main.addEventListener("dd:change", (e) => {
    const name = e.detail.name;
    if (!cur || !name || !e.target.closest(".filters")) return;
    if (name === "feature" || name === "sort") go({ [name]: e.detail.value || null });
    else pending = e.target.closest(".dd");
  });
  // a multi-choice menu applies its picks when it closes: a click outside it, or on its own button
  document.addEventListener("click", (e) => {
    if (!pending || (pending.contains(e.target) && !e.target.closest(".dd-t"))) return;
    const dd = pending;
    pending = null;
    go({ [dd.dataset.name]: picked(dd) });
  }, true);
}

export default { nav: "cases", default: "list", after,
  states: {
    "list": { render: list },
    "filtered": { render: list },
    "filter-open": { render: list },
    "search": { render: list },
    "search-empty": { render: list },
    "search-cleared": { render: list, toast: (d) => `<div><b>Search cleared.</b> <span class="muted">Showing all ${d.total} cases.</span></div>` },
    "empty": { render: empty }
  }
};
