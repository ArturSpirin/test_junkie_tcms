// Drives the real top-bar search code from shell.js in node, with fake key events and a fake document,
// and prints the results as JSON for tests/web/test_search_box.py. Needs only node, no packages.
const JS = new URL("../../src/test_junkie_tcms/web/js/", import.meta.url);
const ui = await import(new URL("ui.js", JS).href);
const data = await import(new URL("./fixtures/data.js", import.meta.url).href);
const shell = await import(new URL("shell.js", JS).href);

// A fake element: editable says whether closest() finds an editable ancestor.
const el = (tag, editable = false) => ({ tagName: tag, closest: (sel) => (editable && sel.includes("input") ? {} : null) });

function page({ modal = false, hidden = false } = {}) {
  const box = { focused: false, selected: false, focus() { this.focused = true; }, select() { this.selected = true; }, getClientRects: () => (hidden ? [] : [{}]) };
  const doc = { querySelector: (sel) => (sel === '[aria-modal="true"]' ? (modal ? {} : null) : sel === "[data-search] input" ? box : null) };
  return { box, doc };
}

function press(target, opts = {}, key = "/", mods = {}) {
  const { box, doc } = page(opts);
  const e = { key, target, ctrlKey: false, metaKey: false, altKey: false, ...mods, prevented: false, preventDefault() { this.prevented = true; } };
  const acted = shell.slashKey(e, doc);
  return { acted, focused: box.focused, selected: box.selected, prevented: e.prevented };
}

const ctx = await data.context();
ui.configure(ctx);
const out = {
  keys: {
    body: press(el("BODY")),
    input: press(el("INPUT", true)),
    textarea: press(el("TEXTAREA", true)),
    contenteditable: press(el("DIV", true)),
    dialog: press(el("BODY"), { modal: true }),
    ctrl: press(el("BODY"), {}, "/", { ctrlKey: true }),
    meta: press(el("BODY"), {}, "/", { metaKey: true }),
    other_key: press(el("BODY"), {}, "k"),
    hidden: press(el("BODY"), { hidden: true })
  },
  href: { empty: shell.searchHref(""), spaces: shell.searchHref("  "), amp: shell.searchHref(" a&b c ") },
  markup: shell.shell("cases", ctx),
  markup_q: shell.shell("cases", ctx, 'refund "x"'),
  load_q: (await data.load("cases", "list", "refund")).q,
  load_no_q: (await data.load("cases", "list")).q ?? null
};
process.stdout.write(JSON.stringify(out));
