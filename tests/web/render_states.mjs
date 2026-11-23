// Renders every state of every app view in node, the way the shell does, and prints the result as JSON:
// { "<view>": { "<state>": { "html": "...", "again": true } | { "error": "..." } } }.
// "again" says a second render of the same data gave the same HTML (render is pure).
// Run by tests/web/test_render.py; needs only node, no packages.
import { readdirSync } from "node:fs";

const JS = new URL("../../src/test_junkie_tcms/web/js/", import.meta.url);
const ui = await import(new URL("ui.js", JS).href);
const data = await import(new URL("data.js", JS).href);
const shell = await import(new URL("shell.js", JS).href);

const ctx = await data.context();
ui.configure(ctx);
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
      const html = view.states[state].render(d);
      const twice = await data.load(id, state);
      twice.ctx = ctx;
      out[id][state] = { html, again: view.states[state].render(twice) === html };
    } catch (e) {
      out[id][state] = { error: String(e?.stack || e) };
    }
  }
}
process.stdout.write(JSON.stringify(out));
