/* Test Junkie TCMS web app: icons and UI helpers, shared by every view.
 Helpers: dd (styled dropdown), tg (toggle), rte (rich-text editor), dr (date range), st/disc (Test Junkie statuses), toast.
 Render helpers return HTML strings and never touch the DOM, so views render in node too; the live behaviour
 (dropdowns, tooltips, editor, date range) is wired once by install(), in the browser only. */
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const sv = (d, s = 16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const I = {
  edit: sv('<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/>'),
  mail: sv('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>'),
  play: sv('<path d="M7 5l12 7-12 7z"/>'),
  wifioff: sv('<path d="M3 3l18 18M8.5 16.5a5 5 0 0 1 7 0M5 12.5a10 10 0 0 1 5-2.6M14 10a10 10 0 0 1 5 2.5M12 20h.01"/>'),
  tree: sv('<path d="M4 5h6M4 5v14M4 12h6M4 19h6"/><rect x="12" y="3" width="8" height="4" rx="1"/><rect x="12" y="10" width="8" height="4" rx="1"/><rect x="12" y="17" width="8" height="4" rx="1"/>'),
  cycle: sv('<path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/>'),
  run: sv('<path d="M7 5l11 7-11 7z"/>'),
  report: sv('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
  audit: sv('<path d="M9 4h6l1 2h3v15H5V6h3z"/><path d="M9 11h6M9 15h4"/>'),
  key: sv('<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>'),
  person: sv('<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>'),
  agent: sv('<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 3v4M9 13h.01M15 13h.01M9 16h6"/>', 14),
  members: sv('<circle cx="9" cy="8" r="3.5"/><path d="M2 20c1-3.5 3.5-5 7-5s6 1.5 7 5M16 4.5a3.5 3.5 0 0 1 0 7M18 15c2 .6 3.4 2.2 4 5"/>'),
  search: sv('<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>'),
  menu: sv('<path d="M4 6h16M4 12h16M4 18h16"/>', 20),
  x: sv('<path d="M6 6l12 12M18 6L6 18"/>'),
  chev: sv('<path d="M9 6l6 6-6 6"/>', 14),
  chevl: sv('<path d="M15 6l-6 6 6 6"/>', 14),
  chevd: sv('<path d="M6 9l6 6 6-6"/>', 14),
  plus: sv('<path d="M12 5v14M5 12h14"/>'),
  grip: sv('<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>'),
  drag: sv('<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>', 14),
  folder: sv('<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>', 15),
  doc: sv('<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>', 15),
  clip: sv('<path d="M21 11l-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7"/>'),
  check: sv('<path d="M5 12l5 5 9-10"/>'),
  trash: sv('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>'),
  copy: sv('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>'),
  restore: sv('<path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5"/><path d="M4 4v4.5h4.5"/>'),
  link: sv('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'),
  filter: sv('<path d="M3 5h18l-7 8v6l-4 2v-8z"/>'),
  more: sv('<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'),
  warn: sv('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>'),
  info: sv('<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>'),
  lock: sv('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>'),
  upload: sv('<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>'),
  sun: sv('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>'),
  md: sv('<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 15V9l3 3 3-3v6M16 9v6M14 13l2 2 2-2"/>'),
  mcp: sv('<path d="M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4"/>'),
  plug: sv('<path d="M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4"/>'),
  bolt: sv('<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>'),
  clock: sv('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  calendar: sv('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
  eyeoff: sv('<path d="M3 3l18 18M10.6 6.1A10 10 0 0 1 12 6c5 0 9 4.5 10 6a17 17 0 0 1-3 3.6M6.5 7.4A17 17 0 0 0 2 12c1 1.5 5 6 10 6a10 10 0 0 0 4-.8"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>'),
  skipf: sv('<path d="M5 5l9 7-9 7zM18 5v14"/>'),
  ban: sv('<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>'),
  alert: sv('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>'),
  xcirc: sv('<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>'),
  okcirc: sv('<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>'),
  dotted: sv('<circle cx="12" cy="12" r="9" stroke-dasharray="3 3"/>'),
  bold: sv('<path d="M7 5h6a3.5 3.5 0 0 1 0 7H7zM7 12h7a3.5 3.5 0 0 1 0 7H7z"/>', 15),
  italic: sv('<path d="M10 5h8M6 19h8M14 5l-4 14"/>', 15),
  underline: sv('<path d="M7 4v7a5 5 0 0 0 10 0V4M5 20h14"/>', 15),
  strike: sv('<path d="M5 12h14M16 6.5A4 4 0 0 0 12 5c-2.5 0-4 1.3-4 3 0 1.4 1 2.3 3 3M8 17.5A4.5 4.5 0 0 0 12 19c2.5 0 4-1.3 4-3.2"/>', 15),
  code: sv('<path d="M8 8l-4 4 4 4M16 8l4 4-4 4"/>', 15),
  ul: sv('<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>', 15),
  ol: sv('<path d="M10 6h10M10 12h10M10 18h10M4 5l1.5-1v5M3.5 14.5c.3-1 2.5-1 2.5.3 0 1-2.5 1.9-2.5 3.2H6"/>', 15),
  checklist: sv('<rect x="3" y="4" width="6" height="6" rx="1.5"/><path d="M4.5 7l1 1 2-2M12 7h9M12 17h9"/><rect x="3" y="14" width="6" height="6" rx="1.5"/>', 15),
  quote: sv('<path d="M6 7h4v5H6c0 3 1 4 3 5M14 7h4v5h-4c0 3 1 4 3 5"/>', 15),
  codeblock: sv('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 10l-2 2 2 2M15 10l2 2-2 2"/>', 15),
  image: sv('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>', 15),
  table: sv('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M10 4v16"/>', 15),
  undo: sv('<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>', 15),
  redo: sv('<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>', 15),
  heading: sv('<path d="M6 4v16M18 4v16M6 12h12"/>', 15),
  spark: sv('<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>'),
  server: sv('<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>'),
  external: sv('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>'),
  tag: sv('<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="8" cy="8" r="1.5"/>'),
  flag: sv('<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>'),
  gear: sv('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>'),
  logout: sv('<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l-5-5 5-5M5 12h11"/>'),
  moon: sv('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'),
  arrowup: sv('<path d="M12 19V5M6 11l6-6 6 6"/>', 14),
  arrowdn: sv('<path d="M12 5v14M6 13l6 6 6-6"/>', 14),
  pin: sv('<path d="M9 4h6l-1 5 3 3v2H7v-2l3-3zM12 14v7"/>', 14),
  build: sv('<path d="M14 6l4 4-9 9H5v-4z"/><path d="M12 8l4 4"/>')
};

/* Set once from data.context() by configure(): people by handle, the org name crumbs start from, and today. */
let people = {};
let orgName = "";
let TODAY = new Date();
export function configure(ctx) {
  people = ctx.people || {};
  orgName = ctx.org ? ctx.org.name : "";
  if (ctx.today) { const [y, m, d] = ctx.today.split("-").map(Number); TODAY = new Date(y, m - 1, d); }
}
/* a person is [name, initials, avatarClass] */
export const person = (h) => people[h] || [h, String(h).slice(0, 2).toUpperCase(), ""];
function actor(kind, name, opt = {}) {
  if (kind === "person") {
    const p = person(name);
    return `<span class="actor"><span class="av person ${p[2]}">${p[1]}</span><span>${p[0]}</span>${opt.k ? '<span class="kind">person</span>' : ""}</span>`;
  }
  if (kind === "agent") return `<span class="actor"><span class="av agent">${I.agent}</span><span>${name}</span>${opt.k !== false ? '<span class="kind">agent</span>' : ""}</span>`;
  return `<span class="actor"><span class="av token">${I.key}</span><span class="mono">${name}</span>${opt.k !== false ? '<span class="kind">token</span>' : ""}</span>`;
}

/* Test Junkie result statuses (test_junkie/constants.py:3-11) plus "untested" for a cycle case with no result yet. */
const STATUS = [
  ["success", "success", I.okcirc, "s"],
  ["fail", "fail", I.xcirc, "f"],
  ["error", "error", I.bolt, "e"],
  ["ignore", "ignore", I.eyeoff, "i"],
  ["skip", "skip", I.skipf, "k"],
  ["cancel", "cancel", I.ban, "c"],
  ["untested", "untested", I.dotted, "u"]
];
const LEGACY = { passed: "success", pass: "success", failed: "fail", blocked: "skip", skipped: "skip", retest: "untested", errored: "error", ignored: "ignore", cancelled: "cancel" };
const norm = (s) => LEGACY[s] || s;
const stIcon = (s) => (STATUS.find((x) => x[0] === norm(s)) || STATUS[6])[2];
const st = (s, opt = {}) => { s = norm(s); return `<span class="st ${s}${opt.lg ? " lg" : ""}">${stIcon(s)}${opt.label === false ? "" : `<span>${opt.label || s}</span>`}</span>`; };
const disc = (n, s) => `<span class="disc ${norm(s || "untested")}">${n}</span>`;
const ver = (n, pin) => `<span class="ver${pin ? " pin" : ""}">v${n}</span>`;
function counts(c) {
  const o = { success: 0, fail: 0, error: 0, ignore: 0, skip: 0, cancel: 0, untested: 0 };
  const leg = { p: "success", f: "fail", b: "skip", s: "skip", r: "untested", u: "untested", e: "error", i: "ignore", c: "cancel" };
  for (const k in c) { const key = o.hasOwnProperty(k) ? k : leg[k]; if (key) o[key] += c[k] || 0; }
  return o;
}
/* ---------- custom tooltip (charts never use the browser title) ---------- */
const tipH = (head, rows, foot) => `<div class="tt-h">${esc(head)}</div>${rows.map(([l, c, v]) => `<div class="tt-r"><span class="dot" style="--c:${c}"></span><span>${esc(l)}</span><b>${esc(String(v))}</b></div>`).join("")}${foot ? `<div class="tt-f"><span>${esc(foot[0])}</span><b>${esc(String(foot[1]))}</b></div>` : ""}`;
const tipA = (head, rows, foot) => ` data-tip="${esc(tipH(head, rows, foot))}" tabindex="0"`;
let tipEl, tipPinned = null;
function showTip(el) {
  if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "tip"; tipEl.setAttribute("role", "tooltip"); document.body.appendChild(tipEl); }
  document.querySelectorAll(".tip-on").forEach((x) => x.classList.remove("tip-on"));
  el.classList.add("tip-on");
  tipEl.innerHTML = el.getAttribute("data-tip");
  tipEl.classList.remove("below"); tipEl.classList.add("show");
  const r = el.getBoundingClientRect(), w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  let x = r.left + r.width / 2 - w / 2; x = Math.max(8, Math.min(window.innerWidth - w - 8, x));
  let y = r.top - h - 10;
  if (y < 64) { y = r.bottom + 10; tipEl.classList.add("below"); }
  tipEl.style.left = x + "px"; tipEl.style.top = y + "px";
  tipEl.style.setProperty("--ax", Math.max(14, Math.min(w - 14, r.left + r.width / 2 - x)) + "px");
}
function hideTip() { if (tipPinned && document.body.contains(tipPinned)) return; if (tipEl) tipEl.classList.remove("show"); document.querySelectorAll(".tip-on").forEach((x) => x.classList.remove("tip-on")); }
function pinTip(el) { if (!el) return; tipPinned = el; requestAnimationFrame(() => showTip(el)); setTimeout(() => { if (tipPinned === el) showTip(el); }, 350); }
function installTips() {
  document.addEventListener("mouseover", (e) => { const el = e.target.closest && e.target.closest("[data-tip]"); if (el) { tipPinned = null; showTip(el); } });
  document.addEventListener("mouseout", (e) => { const el = e.target.closest && e.target.closest("[data-tip]"); if (el && !el.contains(e.relatedTarget)) hideTip(); });
  document.addEventListener("focusin", (e) => { const el = e.target.closest && e.target.closest("[data-tip]"); if (el) showTip(el); });
  document.addEventListener("focusout", (e) => { if (e.target.closest && e.target.closest("[data-tip]")) hideTip(); });
  window.addEventListener("hashchange", () => { tipPinned = null; if (tipEl) tipEl.classList.remove("show"); });
  window.addEventListener("scroll", () => { if (tipEl && tipEl.classList.contains("show")) { const on = document.querySelector(".tip-on"); if (on) showTip(on); } }, true);
}
const STROWS = (o) => STATUS.filter((s) => o[s[0]]).map((s) => [s[0], `var(--st-${s[0]})`, o[s[0]]]);

function bar(c, cls = "", head = "Results") {
  const o = counts(c);
  const sum = Object.values(o).reduce((a, b) => a + b, 0);
  const t = sum || 1;
  const seg = (k) => (o[k] ? `<i class="${k}" style="width:${(o[k] / t) * 100}%"></i>` : "");
  return `<div class="bar ${cls}"${tipA(head, STROWS(o), ["Total", sum])}>${["success", "fail", "error", "ignore", "skip", "cancel"].map(seg).join("")}</div>`;
}
const legend = (c) => {
  const o = c ? counts(c) : null;
  return `<div class="legend">${STATUS.map((s) => `<span style="--c:var(--st-${s[0]})">${s[0]}${o ? ` <b>${o[s[0]]}</b>` : ""}</span>`).join("")}</div>`;
};

/* ---------- dropdown ---------- */
function dd(cfg) {
  const opts = (cfg.options || []).map((o) => (typeof o === "string" && o !== "-" ? { v: o, label: o } : o));
  const multi = !!cfg.multi;
  const vals = multi ? [].concat(cfg.value || []) : [cfg.value];
  const cur = opts.find((o) => o !== "-" && !o.group && vals.includes(o.v));
  const cls = ["dd", cfg.cls || "", cfg.open ? "open" : "", cfg.dis ? "dis" : ""].join(" ").trim();
  const icon = (o) => (o.dot ? `<span class="dd-ic"><span class="dot" style="--c:${o.dot}"></span></span>` : o.icon ? `<span class="dd-ic">${o.icon}</span>` : "");
  let face;
  if (multi) {
    const sel = opts.filter((o) => o !== "-" && !o.group && vals.includes(o.v));
    face = sel.length ? `<span class="dd-chips">${sel.slice(0, 2).map((o) => `<span class="chip">${esc(o.short || o.label)}</span>`).join("")}${sel.length > 2 ? `<span class="chip">+${sel.length - 2}</span>` : ""}</span>` : `<span class="dd-v dd-ph">${esc(cfg.placeholder || "Any")}</span>`;
  } else {
    face = `${cur ? icon(cur) : ""}<span class="dd-v${cur ? "" : " dd-ph"}">${esc(cur ? cur.short || cur.label : cfg.placeholder || "Select…")}</span>`;
  }
  const list = opts.map((o, i) => {
    if (o === "-") return '<div class="dd-sep" role="separator"></div>';
    if (o.group) return `<div class="dd-g">${esc(o.group)}</div>`;
    const sel = vals.includes(o.v);
    return `<div class="dd-o${sel ? " sel" : ""}${o.dis ? " dis" : ""}${o.danger ? " danger" : ""}${cfg.hl === o.v ? " hl" : ""}" role="option" aria-selected="${sel}" data-v="${esc(o.v)}" data-label="${esc(o.short || o.label)}">${icon(o)}<span class="dd-l">${esc(o.label)}${o.hint ? `<small>${esc(o.hint)}</small>` : ""}</span>${o.kbd ? `<kbd>${o.kbd}</kbd>` : ""}<span class="dd-ck">${I.check}</span></div>`;
  }).join("");
  return `<div class="${cls}" data-dd${multi ? ' data-multi' : ""}${cfg.name ? ` data-name="${cfg.name}"` : ""}${cfg.w ? ` style="width:${cfg.w}"` : ""}>
<button type="button" class="dd-t" aria-haspopup="listbox" aria-expanded="${!!cfg.open}"${cfg.label ? ` aria-label="${esc(cfg.label)}"` : ""}>${cfg.pre ? `<span class="dd-pre">${esc(cfg.pre)}</span>` : ""}${face}<span class="dd-c">${I.chevd}</span></button>
<div class="dd-m" role="listbox"${multi ? ' aria-multiselectable="true"' : ""}>${cfg.search ? `<label class="dd-s">${I.search}<input placeholder="${esc(cfg.search === true ? "Search…" : cfg.search)}" value="${esc(cfg.q || "")}" aria-label="Filter options"></label>` : ""}<div class="dd-list">${list}<div class="dd-empty" hidden>No matches</div></div>${cfg.foot ? `<div class="dd-ft">${cfg.foot}</div>` : ""}</div></div>`;
}
function ddFit(d) {
  const m = d.querySelector(".dd-m");
  if (!m) return;
  d.classList.remove("right");
  const r = m.getBoundingClientRect();
  if (r.right > window.innerWidth - 8) d.classList.add("right");
}
function ddClose(except) {
  document.querySelectorAll(".dd.open").forEach((d) => { if (d !== except) { d.classList.remove("open"); d.querySelector(".dd-t").setAttribute("aria-expanded", "false"); } });
}

/* ---------- toggle ---------- */
const tg = (on, label, hint, o = {}) => `<label class="tg ${o.cls || ""}"><input type="checkbox" role="switch"${on ? " checked" : ""}${o.disabled ? " disabled" : ""}${o.name ? ` name="${o.name}"` : ""}><span class="tg-s"></span>${label || hint ? `<span class="tg-t">${label || ""}${hint ? `<small>${hint}</small>` : ""}</span>` : ""}</label>`;

/* ---------- rich-text editor ---------- */
const TB_FULL = ["style", "|", "bold", "italic", "underline", "strike", "code", "|", "ul", "ol", "checklist", "|", "quote", "codeblock", "|", "link", "image", "table", "|", "undo", "redo", "sp", "md"];
const TB_COMPACT = ["bold", "italic", "underline", "code", "|", "ul", "ol", "checklist", "|", "link", "image", "sp", "md"];
const TB = {
  bold: [I.bold, "Bold", "bold", "Ctrl+B"], italic: [I.italic, "Italic", "italic", "Ctrl+I"], underline: [I.underline, "Underline", "underline", "Ctrl+U"],
  strike: [I.strike, "Strikethrough", "strikeThrough"], code: [I.code, "Inline code", "code", "Ctrl+E"], ul: [I.ul, "Bulleted list", "insertUnorderedList"],
  ol: [I.ol, "Numbered list", "insertOrderedList"], checklist: [I.checklist, "Checklist", "checklist"], quote: [I.quote, "Quote", "quote"],
  codeblock: [I.codeblock, "Code block", "codeblock"], link: [I.link, "Link", "link", "Ctrl+K"], image: [I.image, "Image or attachment", "image"],
  table: [I.table, "Table", "table"], undo: [I.undo, "Undo", "undo", "Ctrl+Z"], redo: [I.redo, "Redo", "redo", "Ctrl+Shift+Z"]
};
const STYLE_OPTS = [{ v: "p", label: "Paragraph", kbd: "Ctrl+Alt+0" }, { v: "h1", label: "Heading 1", kbd: "Ctrl+Alt+1" }, { v: "h2", label: "Heading 2", kbd: "Ctrl+Alt+2" }, { v: "h3", label: "Heading 3", kbd: "Ctrl+Alt+3" }, "-", { v: "blockquote", label: "Quote" }, { v: "pre", label: "Code block" }];
function rte(c = {}) {
  const items = c.toolbar || (c.compact ? TB_COMPACT : TB_FULL);
  const on = c.on || [];
  const bar = items.map((k) => {
    if (k === "|") return '<span class="sep"></span>';
    if (k === "sp") return '<span class="sp"></span>';
    if (k === "style") return dd({ value: c.style || "p", options: STYLE_OPTS, cls: "sm rte-style", label: "Text style", open: c.styleOpen });
    if (k === "md") return `<button type="button" class="mdt${c.md ? " on" : ""}" data-cmd="md" title="Edit as Markdown" aria-pressed="${!!c.md}">${I.md}<span>MD</span></button>`;
    const b = TB[k];
    return `<button type="button" class="${on.includes(k) ? "on" : ""}" data-cmd="${b[2]}" title="${b[1]}${b[3] ? " (" + b[3] + ")" : ""}" aria-label="${b[1]}">${b[0]}</button>`;
  }).join("");
  /* the Markdown view shows c.mdText, the source text the server stores, so rendering needs no DOM */
  const body = c.md ? `<div class="ed rich src" contenteditable="true" spellcheck="false" data-ph="${esc(c.placeholder || "")}">${esc(c.mdText || "")}</div>` : `<div class="ed rich" contenteditable="${c.ro ? "false" : "true"}" data-ph="${esc(c.placeholder || "Write…")}"${c.label ? ` aria-label="${esc(c.label)}"` : ""}>${c.html || ""}</div>`;
  return `<div class="rte${c.compact ? " compact" : ""}${c.focus ? " is-focus" : ""}${c.ro ? " ro" : ""}${c.cls ? " " + c.cls : ""}" data-rte>${c.ro ? "" : `<div class="rtb" role="toolbar" aria-label="Formatting">${bar}</div>`}${body}${c.foot ? `<div class="rfoot">${c.foot}</div>` : ""}</div>`;
}
function toMd(h) {
  const d = document.createElement("div");
  d.innerHTML = h;
  const walk = (n, ctx = {}) => {
    if (n.nodeType === 3) return n.textContent;
    const kids = () => [...n.childNodes].map((k) => walk(k, ctx)).join("");
    switch (n.nodeName) {
      case "B": case "STRONG": return `**${kids()}**`;
      case "I": case "EM": return `_${kids()}_`;
      case "S": case "STRIKE": return `~~${kids()}~~`;
      case "U": return `<u>${kids()}</u>`;
      case "CODE": return ctx.pre ? kids() : "`" + kids() + "`";
      case "A": return `[${kids()}](${n.getAttribute("href")})`;
      case "H1": return `# ${kids()}\n\n`; case "H2": return `## ${kids()}\n\n`; case "H3": return `### ${kids()}\n\n`;
      case "P": case "DIV": return `${kids()}\n\n`;
      case "BR": return "\n";
      case "BLOCKQUOTE": return kids().trim().split("\n").map((l) => "> " + l).join("\n") + "\n\n";
      case "PRE": return "```\n" + [...n.childNodes].map((k) => walk(k, { pre: true })).join("") + "\n```\n\n";
      case "UL": return [...n.children].map((li) => (n.classList.contains("cl") ? `- [${li.classList.contains("done") ? "x" : " "}] ` : "- ") + walk(li).trim()).join("\n") + "\n\n";
      case "OL": return [...n.children].map((li, i) => `${i + 1}. ` + walk(li).trim()).join("\n") + "\n\n";
      case "TABLE": { const rows = [...n.querySelectorAll("tr")].map((tr) => "| " + [...tr.children].map((td) => td.textContent.trim()).join(" | ") + " |"); if (rows.length) rows.splice(1, 0, "|" + " --- |".repeat(n.querySelector("tr").children.length)); return rows.join("\n") + "\n\n"; }
      case "SPAN": if (n.classList.contains("img")) return `![${n.textContent.trim()}](attachment)`; return kids();
      default: return kids();
    }
  };
  return walk(d).replace(/\n{3,}/g, "\n\n").trim();
}
function rteCmd(r, cmd) {
  const ed = r.querySelector(".ed");
  if (cmd === "md") {
    const b = r.querySelector(".mdt");
    if (ed.classList.contains("src")) { ed.classList.remove("src"); ed.innerHTML = ed.dataset.html || ""; b.classList.remove("on"); b.setAttribute("aria-pressed", "false"); }
    else { ed.dataset.html = ed.innerHTML; ed.textContent = toMd(ed.innerHTML); ed.classList.add("src"); b.classList.add("on"); b.setAttribute("aria-pressed", "true"); }
    return;
  }
  if (ed.classList.contains("src")) return;
  ed.focus();
  const ins = (html) => document.execCommand("insertHTML", false, html);
  const sel = () => String(window.getSelection() || "") || "";
  if (cmd === "code") ins(`<code>${esc(sel() || "code")}</code>`);
  else if (cmd === "link") ins(`<a href="https://example.com">${esc(sel() || "link")}</a>`);
  else if (cmd === "checklist") ins('<ul class="cl"><li>Check item</li></ul>');
  else if (cmd === "quote") document.execCommand("formatBlock", false, "blockquote");
  else if (cmd === "codeblock") ins(`<pre><code>${esc(sel() || "curl -s $TCMS/api/v1/health")}</code></pre>`);
  else if (cmd === "image") ins(`<span class="img">${I.image} screenshot.png</span>&nbsp;`);
  else if (cmd === "table") ins("<table><tr><th>Field</th><th>Value</th></tr><tr><td>email</td><td>user@example.com</td></tr></table><p></p>");
  else document.execCommand(cmd, false, null);
  rteSync(r);
}
function rteSync(r) {
  r.querySelectorAll(".rtb button[data-cmd]").forEach((b) => {
    const c = b.dataset.cmd;
    if (["bold", "italic", "underline", "strikeThrough", "insertUnorderedList", "insertOrderedList"].includes(c)) {
      try { b.classList.toggle("on", document.queryCommandState(c)); } catch (e) { /* ignore */ }
    }
  });
}

/* ---------- date range ---------- */
const daysAgo = (n) => new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate() - n);
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const DR = [["today", "Today"], ["7d", "7D"], ["14d", "14D"], ["30d", "30D"], ["custom", "Custom"]];
const fmt = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
function cal(y, m, a, b) {
  const first = new Date(y, m, 1), start = new Date(y, m, 1 - first.getDay());
  let g = ["S", "M", "T", "W", "T", "F", "S"].map((w) => `<span class="w">${w}</span>`).join("");
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    const c = ["d"];
    if (d.getMonth() !== m) c.push("out");
    else {
      if (d > TODAY) c.push("fut");
      if (+d === +TODAY) c.push("today");
      if (a && b && d > a && d < b) c.push("in");
      if (a && +d === +a) c.push("a");
      if (b && +d === +b) c.push("b");
    }
    g += `<span class="${c.join(" ")}" data-day="${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}">${d.getDate()}</span>`;
    if (i === 34 && new Date(start.getFullYear(), start.getMonth(), start.getDate() + 35).getMonth() !== m) break;
  }
  const name = first.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  return `<div class="cal"><div class="cal-h"><button type="button" class="icon-btn sm" aria-label="Previous month">${I.chevl}</button><span>${name}</span><button type="button" class="icon-btn sm" aria-label="Next month">${I.chev}</button></div><div class="cal-g">${g}</div></div>`;
}
function drLabel(v, from, to) {
  if (v === "custom" && from && to) return `${fmt(from)} – ${fmt(to)}`;
  const n = { today: 0, "7d": 6, "14d": 13, "30d": 29 }[v] || 0;
  return n ? `${fmt(daysAgo(n))} – ${fmt(TODAY)}` : `Today, ${fmt(TODAY)}`;
}
function dr(c = {}) {
  const v = c.value || "today";
  /* c.from / c.to are Dates; the default custom range is the week ending five days ago */
  const from = c.from || daysAgo(12), to = c.to || daysAgo(5);
  const prev = new Date(to.getFullYear(), to.getMonth() - 1, 1);
  const seg = DR.map(([k, l]) => `<button type="button" data-dr="${k}" class="${k === v ? "on" : ""}" aria-pressed="${k === v}">${k === "custom" ? I.calendar + " " : ""}${v === "custom" && k === "custom" && c.applied ? drLabel("custom", from, to) : l}</button>`).join("");
  const pre = [["Today", "today"], ["Yesterday", "y"], ["Last 7 days", "7d"], ["Last 14 days", "14d"], ["Last 30 days", "30d"], ["This month", "m"], ["Last month", "lm"], ["Since last release", "rel"]];
  return `<div class="dr${c.open ? " open" : ""}" data-drw data-value="${v}">
<div class="seg" role="group" aria-label="Date range">${seg}</div>
<div class="dr-pop" role="dialog" aria-label="Custom date range">
<div class="dr-pre">${pre.map(([l, k]) => `<button type="button" data-pre="${k}" class="${k === "x" ? "on" : ""}">${l}</button>`).join("")}</div>
<div class="dr-body"><div class="dr-cals">${cal(prev.getFullYear(), prev.getMonth(), from, to)}${cal(to.getFullYear(), to.getMonth(), from, to)}</div>
<div class="dr-ft"><input class="in mono" value="${iso(from)}" aria-label="From"><span class="muted">→</span><input class="in mono" value="${iso(to)}" aria-label="To"><span class="sp"></span><span class="faint hide-n">Times in PT</span><button type="button" class="btn ghost sm" data-drx="cancel">Cancel</button><button type="button" class="btn primary sm" data-drx="apply">Apply</button></div></div>
</div></div>`;
}

/* ---------- toast ---------- */
function toast(html, err, keep) {
  document.querySelectorAll(".toast.live-t").forEach((t) => t.remove());
  document.body.insertAdjacentHTML("beforeend", `<div class="toast live-t${err ? " err" : ""}" role="status">${html}</div>`);
  if (!keep) setTimeout(() => document.querySelectorAll(".toast.live-t").forEach((t) => t.remove()), 3200);
}

/* ---------- dropdown ids ----------
   dd() renders no id, so render stays pure; each menu gets its document-unique id (for aria-controls)
   when it enters the page, whichever code put it there. */
let ddN = 0;
function ddIds() {
  document.querySelectorAll(".dd-m:not([id])").forEach((m) => {
    m.id = "dd" + ++ddN;
    m.closest(".dd").querySelector(".dd-t").setAttribute("aria-controls", m.id);
  });
}
function installIds() {
  ddIds();
  new MutationObserver(ddIds).observe(document.body, { childList: true, subtree: true });
}

/* ---------- live delegation ---------- */
function installLive() {
  document.addEventListener("click", (e) => {
    const t = e.target;
    if (t.closest("[data-back]")) { history.back(); return; }
    const trig = t.closest(".dd-t");
    if (trig) {
      const d = trig.parentElement;
      if (d.classList.contains("dis")) return;
      ddClose(d);
      const open = d.classList.toggle("open");
      trig.setAttribute("aria-expanded", open);
      if (open) { ddFit(d); const s = d.querySelector(".dd-s input"); if (s) s.focus(); }
      return;
    }
    const o = t.closest(".dd-o");
    if (o && !o.classList.contains("dis")) {
      const d = o.closest(".dd");
      if (d.hasAttribute("data-multi")) {
        o.classList.toggle("sel");
        const sel = [...d.querySelectorAll(".dd-o.sel")];
        const face = d.querySelector(".dd-chips, .dd-v");
        const html = sel.length ? `<span class="dd-chips">${sel.slice(0, 2).map((x) => `<span class="chip">${esc(x.dataset.label)}</span>`).join("")}${sel.length > 2 ? `<span class="chip">+${sel.length - 2}</span>` : ""}</span>` : '<span class="dd-v dd-ph">Any</span>';
        face.outerHTML = html;
      } else {
        d.querySelectorAll(".dd-o").forEach((x) => { x.classList.remove("sel"); x.setAttribute("aria-selected", "false"); });
        o.classList.add("sel"); o.setAttribute("aria-selected", "true");
        const v = d.querySelector(".dd-t .dd-v");
        if (v) { v.textContent = o.dataset.label; v.classList.remove("dd-ph"); }
        const ic = d.querySelector(".dd-t > .dd-ic"), oic = o.querySelector(".dd-ic");
        if (ic && oic) ic.innerHTML = oic.innerHTML;
        d.classList.remove("open");
        const r = d.closest("[data-rte]");
        if (r && d.classList.contains("rte-style")) { const ed = r.querySelector(".ed"); ed.focus(); document.execCommand("formatBlock", false, o.dataset.v); }
      }
      d.dispatchEvent(new CustomEvent("dd:change", { bubbles: true, detail: { value: o.dataset.v, name: d.dataset.name } }));
      return;
    }
    if (!t.closest(".dd")) ddClose();

    const rb = t.closest(".rtb button[data-cmd]");
    if (rb) { e.preventDefault(); rteCmd(rb.closest("[data-rte]"), rb.dataset.cmd); return; }
    const cli = t.closest(".ed ul.cl li");
    if (cli && e.offsetX < 24) cli.classList.toggle("done");

    const w = t.closest("[data-drw]");
    const drb = t.closest("[data-dr]");
    if (drb && w) {
      const v = drb.dataset.dr;
      w.querySelectorAll("[data-dr]").forEach((b) => { b.classList.toggle("on", b === drb); b.setAttribute("aria-pressed", b === drb); });
      if (v === "custom") w.classList.toggle("open"); else w.classList.remove("open");
      w.dataset.value = v;
      if (v !== "custom") document.dispatchEvent(new CustomEvent("dr:change", { detail: { value: v } }));
      return;
    }
    const day = t.closest(".cal-g .d:not(.out):not(.fut)");
    if (day && w) {
      const all = [...w.querySelectorAll(".cal-g .d:not(.out)")];
      const a = w.querySelector(".cal-g .d.a"), b = w.querySelector(".cal-g .d.b");
      if (!a || b) { all.forEach((x) => x.classList.remove("a", "b", "in")); day.classList.add("a"); }
      else {
        let i = all.indexOf(a), j = all.indexOf(day);
        if (j < i) { a.classList.remove("a"); day.classList.add("a"); a.classList.add("b"); [i, j] = [j, i]; } else day.classList.add("b");
        all.slice(i + 1, j).forEach((x) => x.classList.add("in"));
      }
      return;
    }
    const pre = t.closest(".dr-pre button");
    if (pre && w) { w.querySelectorAll(".dr-pre button").forEach((b) => b.classList.toggle("on", b === pre)); return; }
    const x = t.closest("[data-drx]");
    if (x && w) {
      w.classList.remove("open");
      if (x.dataset.drx === "apply") {
        const a = w.querySelector(".cal-g .d.a"), b = w.querySelector(".cal-g .d.b") || a;
        const p = (el) => { const [y, m, d] = el.dataset.day.split("-").map(Number); return new Date(y, m - 1, d); };
        if (a) w.querySelector('[data-dr="custom"]').innerHTML = `${I.calendar} ${drLabel("custom", p(a), p(b))}`;
        document.dispatchEvent(new CustomEvent("dr:change", { detail: { value: "custom" } }));
      }
      return;
    }
    if (!t.closest("[data-drw]")) document.querySelectorAll(".dr.open").forEach((d) => { if (!d.hasAttribute("data-pinned")) d.classList.remove("open"); });
  });
  document.addEventListener("input", (e) => {
    const s = e.target.closest(".dd-s input");
    if (!s) return;
    const d = s.closest(".dd"), q = s.value.toLowerCase();
    let n = 0;
    d.querySelectorAll(".dd-o").forEach((o) => { const hit = o.textContent.toLowerCase().includes(q); o.hidden = !hit; if (hit) n++; });
    d.querySelectorAll(".dd-g, .dd-sep").forEach((g) => (g.hidden = !!q));
    d.querySelector(".dd-empty").hidden = n > 0;
  });
  document.addEventListener("keydown", (e) => {
    const d = e.target.closest && e.target.closest(".dd");
    if (e.key === "Escape") { ddClose(); document.querySelectorAll(".dr.open").forEach((x) => x.classList.remove("open")); return; }
    if (!d) return;
    const opts = [...d.querySelectorAll(".dd-o:not(.dis):not([hidden])")];
    if (!opts.length) return;
    let i = opts.findIndex((o) => o.classList.contains("hl"));
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!d.classList.contains("open")) { d.classList.add("open"); ddFit(d); }
      if (i < 0) i = opts.findIndex((o) => o.classList.contains("sel"));
      opts.forEach((o) => o.classList.remove("hl"));
      i = e.key === "ArrowDown" ? Math.min(opts.length - 1, i + 1) : Math.max(0, i - 1);
      opts[i].classList.add("hl"); opts[i].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter" && d.classList.contains("open") && i >= 0) { e.preventDefault(); opts[i].click(); }
  });
  document.addEventListener("selectionchange", () => {
    const n = document.getSelection() && document.getSelection().anchorNode;
    const r = n && (n.nodeType === 1 ? n : n.parentElement) && (n.nodeType === 1 ? n : n.parentElement).closest("[data-rte]");
    if (r) rteSync(r);
  });
}

/* wires tooltips, dropdowns, the editor and the date range to the document; browser only, called once by main.js */
export function install() { installTips(); installLive(); installIds(); }

const modal = (title, body, foot, cls = "") => `<div class="modal-back"><div class="modal ${cls}" role="dialog" aria-modal="true" aria-label="${title}">
  <div class="mh"><h2>${title}</h2><button class="icon-btn" aria-label="Close" data-back>${I.x}</button></div>
  <div class="mb">${body}</div>${foot ? `<div class="mf">${foot}</div>` : ""}</div></div>`;

/* links name a view and its state as "<view>.html#<state>"; the app serves every view from one page, ?view=<view> */
const lnk = (h) => {
  if (h.startsWith("#") || h.startsWith("?") || /^[a-z]+:/i.test(h)) return h;
  const [p, f] = h.split("#");
  return `?view=${p.replace(/\.html$/, "")}${f !== undefined ? "#" + f : ""}`;
};
/* breadcrumbs follow the model: org › product › version|feature › … ; items are [label, href?, cls?] */
const crumbs = (items) => `<div class="crumbs">${[[esc(orgName)]].concat(items).map(([l, h, c]) => (h ? `<a href="${lnk(h)}"${c ? ` class="${c}"` : ""}>${l}</a>` : `<span${c ? ` class="${c}"` : ""}>${l}</span>`)).join('<span class="sep">/</span>')}</div>`;
/* on-page search: o = { q, ph, cnt, clear, extra }. With a query it shows the clear (×) button and the result count. */
const psearch = (o) => `<div class="psearch"><label class="in-ic">${I.search}<input class="in" value="${esc(o.q || "")}" placeholder="${o.ph}" aria-label="${o.ph}">${o.q ? `<a class="x" href="${lnk(o.clear)}" aria-label="Clear search">${I.x}</a>` : ""}</label>${o.q ? `<span class="cnt">${o.cnt}</span>` : ""}${o.extra || ""}</div>`;
const hl = (s, q) => (q ? s.replace(new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>") : s);

export { psearch, hl, I, actor, st, disc, ver, bar, legend, counts, tipH, tipA, pinTip, crumbs, lnk, STATUS, dd, ddFit, tg, rte, toMd, dr, toast, modal, esc };

