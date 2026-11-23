// Renders every state of every app view in node from the mock fixtures (tests/web/fixtures), the way the shell
// does, and prints the result as JSON:
// { "<view>": { "<state>": { "html": "...", "toast": "...", "data": [...], "again": true } | { "error": "..." } } }.
// "toast" is the state's own toast markup (state.toast, shown by the shell after render), "" when it has none.
// "data" is every string in the state's loaded data: what the server or a user wrote, which the UI shows raw.
// "again" says a second render of the same data gave the same HTML (render is pure).
// Run by tests/web/test_render.py; needs only node, no packages.
import { readdirSync } from "node:fs";

const JS = new URL("../../src/test_junkie_tcms/web/js/", import.meta.url);
const ui = await import(new URL("ui.js", JS).href);
const data = await import(new URL("./fixtures/data.js", import.meta.url).href);
const shell = await import(new URL("shell.js", JS).href);

const ctx = await data.context();
ui.configure(ctx);
const strings = (v, into = new Set(), seen = new Set()) => {
  if (typeof v === "string") into.add(v);
  else if (v && typeof v === "object" && !seen.has(v)) {
    seen.add(v);
    for (const x of Object.values(v)) strings(x, into, seen);
  }
  return into;
};
const out = {};
for (const file of readdirSync(new URL("views/", JS)).filter((f) => f.endsWith(".js")).sort()) {
  const id = file.slice(0, -3);
  const view = (await import(new URL(`views/${file}`, JS).href)).default;
  shell.shell(view.nav, ctx);
  out[id] = {};
  for (const state of Object.keys(view.states)) {
    try {
      const d = await data.load(id, state);
      d.ctx = ctx;
      const s = view.states[state];
      const html = s.render(d);
      const toast = s.toast ? ui.toastHtml(s.toast(d)) : "";
      const twice = await data.load(id, state);
      twice.ctx = ctx;
      out[id][state] = { html, toast, data: [...strings(d)], again: s.render(twice) === html };
    } catch (e) {
      out[id][state] = { error: String(e?.stack || e) };
    }
  }
}
process.stdout.write(JSON.stringify(out));
