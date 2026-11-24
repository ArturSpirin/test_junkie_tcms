/* Small helpers the adapters share to map API shapes onto the shapes the views render. No data, no calls. */

const MARKS = ["", "b", "c"];
/* a product's or org's mark colour, stable for its key */
export const markCls = (key) => MARKS[[...String(key)].reduce((n, ch) => n + ch.charCodeAt(0), 0) % MARKS.length];

export const initials = (name) => String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

/* "2026-11-27" or an ISO time as "Nov 27" (day: true adds the weekday, "Fri Nov 27") */
export function day(iso, opt = {}) {
  if (!iso) return "";
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(iso + "T00:00:00") : new Date(iso);
  return d.toLocaleDateString("en-US", { ...(opt.day ? { weekday: "short" } : {}), month: "short", day: "numeric" }).replace(",", "");
}

/* today in the browser's zone, "YYYY-MM-DD" */
export const today = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/* the result counts a results bar draws: the statuses with a count, from a ReportCounts */
const RESULTS = ["success", "fail", "error", "ignore", "skip", "cancel", "untested"];
export const results = (counts) => Object.fromEntries(RESULTS.filter((s) => counts && counts[s]).map((s) => [s, counts[s]]));

/* a version's date line: "Released Oct 30", "Target Dec 18", "Cancelled", "No target date" */
export function when(r, target = "Target") {
  if (r.status === "released" && r.released_at) return `Released ${day(r.released_at)}`;
  if (r.status === "cancelled") return "Cancelled";
  return r.target_date ? `${target} ${day(r.target_date)}` : "No target date";
}

/* the version a product is on: the first in progress, else the first planned, else the newest */
export const current = (releases) => releases.find((r) => r.status === "in_progress") || releases.find((r) => r.status === "planned") || releases[0] || null;

/* a feature tree (FeatureNode with children) flattened in order, each with its "A › B" path and depth */
export function flatten(nodes, parents = [], out = []) {
  for (const n of nodes || []) {
    const path = [...parents, n.name];
    out.push({ ...n, path: path.join(" › "), depth: parents.length });
    flatten(n.children, path, out);
  }
  return out;
}

/* a Markdown field (rich=markdown, the default) as one line, as written */
export const plain = (md) => String(typeof md === "string" ? md : (md && md.markdown) || "").replace(/\s+/g, " ").trim();
