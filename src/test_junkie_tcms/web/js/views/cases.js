/* Test cases: every case in a product across features, with search, filters and sort. */
import { I, st, ver, dd, esc, psearch, hl, crumbs, lnk, footBar } from "../ui.js";

const PRI_COL = { critical: "var(--fail)", high: "var(--blocked)", medium: "var(--retest)", low: "var(--faint)" };
const AUTO_IC = { manual: I.person, automated: I.bolt, to_automate: I.spark };
const filtered = (f) => !!(f.feature.length || f.status.length || f.result.length);

const head = (d) => `${crumbs([[esc(`${d.product.key} · ${d.product.name}`), "products.html#detail"], ["Test cases"]])}<div class="ph"><div class="ttl"><span class="eyebrow">Features and cases · ${esc(d.product.key)}</span><h1>Test cases</h1></div><div class="actions"><a class="btn hide-n" href="${lnk("tree.html")}">${I.tree}View as feature tree</a><a class="btn primary" href="${lnk("case.html#new-case")}">${I.plus}New case</a></div></div>`;

function filters(d) {
  const f = d.filter;
  const v = filtered(f);
  const featOpts = [{ group: `Features in ${d.product.key}` }, ...d.features.map((x) => ({ v: x.id, label: x.path, short: x.short, hint: `${x.cases} cases`, icon: I.folder })),
    "-", { v: "none", label: "No feature yet", hint: `${d.unfiled} cases`, icon: I.dotted }];
  const lifeOpts = [{ group: "Case status" },
    { v: "draft", label: "draft", hint: "Work in progress", dot: "var(--faint)" },
    { v: "ready", label: "ready", hint: "Can be added to cycles", dot: "var(--pass)" },
    { v: "deprecated", label: "deprecated", hint: "Kept for history", dot: "var(--untested)" }];
  const resultOpts = [{ group: "Last Test Junkie result" }, ...["success", "fail", "error", "ignore", "skip", "cancel"].map((r) => ({ v: r, label: r, dot: `var(--st-${r})` })), "-", { v: "untested", label: "untested", dot: "var(--st-untested)" }];
  const autoOpts = [{ group: "Automation" }, ...Object.keys(AUTO_IC).map((a) => ({ v: a, label: a, icon: AUTO_IC[a] }))];
  const priOpts = [{ group: "Priority" }, ...Object.keys(PRI_COL).map((p) => ({ v: p, label: p, dot: PRI_COL[p] }))];
  const sortOpts = [{ group: "Sort cases by" }, { v: "key", label: "Key", icon: I.tag }, { v: "title", label: "Title A to Z", icon: I.doc }, { v: "updated", label: "Last updated", icon: I.clock }, { v: "result", label: "Last result, fail first", icon: I.okcirc }, { v: "priority", label: "Priority, critical first", icon: I.flag }];
  return `<div class="filters">
    ${dd({ multi: true, value: f.feature, options: featOpts, search: "Find a feature", pre: "Feature", placeholder: "Any", cls: "sm", w: "200px", label: "Feature", open: d.open === "feature" })}
    ${dd({ multi: true, value: f.status, options: lifeOpts, pre: "Status", placeholder: "Any", cls: "sm", w: "184px", label: "Status" })}
    ${dd({ multi: true, value: f.result, options: resultOpts, pre: "Last result", placeholder: "Any", cls: "sm", w: "180px", label: "Last result" })}
    ${dd({ multi: true, value: [], options: autoOpts, pre: "Automation", placeholder: "Any", cls: "sm hide-n", w: "190px", label: "Automation" })}
    ${dd({ multi: true, value: [], options: priOpts, pre: "Priority", placeholder: "Any", cls: "sm hide-n", w: "150px", label: "Priority" })}
    ${v ? '<a class="btn ghost sm" href="#list">Clear filters</a>' : ""}<span class="sp"></span>
    ${dd({ value: d.sort, options: sortOpts, pre: "Sort", cls: "sm ghost", w: "196px", label: "Sort" })}
  </div>`;
}

function table(list, q) {
  const tags = (c) => c.tags.map((t) => "#" + esc(t)).join(" ");
  const pri = (p) => `<span class="pri"><span class="dot" style="--c:${PRI_COL[p]}"></span>${p}</span>`;
  const go = `data-href="${lnk("case.html")}"`;
  const rowsH = list.map((c) => `<tr class="${c.status === "deprecated" ? "dim" : ""}" ${go}>
    <td class="key">${hl(esc(c.key), q)}</td>
    <td class="tt"><a href="${lnk("case.html")}" class="ell" title="${esc(c.title)}">${hl(esc(c.title), q)}</a><div class="fpath ell">${I.folder} ${esc(c.feature)}${c.tags.length ? " · " + tags(c) : ""}</div></td>
    <td>${ver(c.version)}</td><td><span class="pill ${c.status}">${c.status}</span></td><td>${st(c.result)}</td>
    <td class="hide-m"><span class="auto">${AUTO_IC[c.automation]}${c.automation}</span></td><td class="hide-m">${pri(c.priority)}</td><td class="hide-m faint" style="font-size:12px;white-space:nowrap">${esc(c.updated)}</td></tr>`).join("");
  const mrows = list.map((c) => `<a class="it" href="${lnk("case.html")}"><div class="row"><span class="key">${hl(esc(c.key), q)}</span>${ver(c.version)}<span class="pill ${c.status}">${c.status}</span>${st(c.result)}</div><b style="font-weight:500">${hl(esc(c.title), q)}</b><span class="faint" style="font-size:12px">${esc(c.feature)}</span><span class="auto">${AUTO_IC[c.automation]}${c.automation} · ${c.priority}</span></a>`).join("");
  return `<div class="tbl-wrap mswap"><table class="t"><thead><tr><th>Key</th><th>Title and feature</th><th>Version</th><th>Status</th><th>Last result</th><th class="hide-m">Automation</th><th class="hide-m">Priority</th><th class="hide-m">Updated</th></tr></thead><tbody>${rowsH}</tbody></table></div><div class="mlist">${mrows}</div>`;
}

const noHits = (d, q) => `<div class="empty"><div class="ill">${I.search}</div><h3>No cases match “${esc(q)}”</h3><p class="muted" style="margin:0 auto 14px;max-width:440px">Search looks at case keys, titles, steps and tags in ${esc(d.product.key)}. Try a key such as “${esc(d.product.key)}-101” or a word from a title.</p><a class="btn" href="${lnk("cases.html#search-cleared")}">Clear search</a></div>`;

function list(d) {
  const q = d.q;
  const f = d.filter;
  const v = filtered(f);
  const P = esc(d.product.key);
  const paths = d.features.filter((x) => f.feature.includes(x.id)).map((x) => x.path);
  let rows = d.cases;
  if (f.feature.length) rows = rows.filter((c) => paths.some((p) => c.feature === p || c.feature.startsWith(p + " ›")));
  if (f.status.length) rows = rows.filter((c) => f.status.includes(c.status));
  if (f.result.length) rows = rows.filter((c) => f.result.includes(c.result));
  if (q) rows = rows.filter((c) => (c.key + " " + c.title + " " + c.tags.join(", ") + " " + c.feature).toLowerCase().includes(q.toLowerCase()));
  const shown = q || v ? rows.length : d.total;
  const cnt = rows.length + (rows.length === 1 ? " case" : " cases");
  return head(d) + `<div class="sub" style="margin-bottom:16px">Every test case in ${P}, across all features. Pick a case to open it in the editor.</div>` +
    psearch({ q, ph: "Search cases by key, title, step or tag", cnt, clear: lnk("cases.html#search-cleared") }) + filters(d) +
    `<div class="card"><div class="hd"><h2>Cases in ${P}</h2><span class="r faint" style="font-size:12px">${q || v ? `${shown} of ${d.total}` : `showing ${rows.length} of ${d.total}`}</span></div>${rows.length ? table(rows, q) : noHits(d, q)}${rows.length && !q && !v ? footBar(`<button class="btn sm">Load 50 more</button>`, `${rows.length} of ${d.total} cases`) : ""}</div>`;
}

const empty = (d) => {
  const P = esc(d.product.key);
  return `${crumbs([[esc(`${d.product.key} · ${d.product.name}`), "products.html#detail"], ["Test cases"]])}<div class="ph"><div class="ttl"><span class="eyebrow">Features and cases · ${P}</span><h1>Test cases</h1></div><div class="actions"><a class="btn primary" href="${lnk("case.html#new-case")}">${I.plus}New case</a></div></div>
  <div class="card"><div class="hd"><h2>Cases in ${P}</h2></div><div class="empty"><div class="ill">${I.doc}</div><h3>No test cases in ${P} yet</h3><p class="muted" style="margin:0 auto 14px;max-width:460px">Write a case by hand, import a CSV, or let an agent draft cases through MCP. Cases can go under a feature now or later.</p><a class="btn" href="${lnk("tree.html")}">${I.tree}Add features first</a> <a class="btn primary" href="${lnk("case.html#new-case")}">${I.plus}New case</a></div></div>`;
};

export default { nav: "cases", default: "list",
  /* a click anywhere on a table row opens the case */
  after: (main) => {
    if (main._cases) return;
    main._cases = true;
    main.addEventListener("click", (e) => { const tr = e.target.closest("tr[data-href]"); if (tr && !e.target.closest("a")) location.href = tr.dataset.href; });
  },
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
