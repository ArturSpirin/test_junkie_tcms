// Runs the feature tree's keyboard functions on the real tree data, under node, and prints the results as JSON.
// Run by tests/web/test_tree_keys.py; needs only node, no packages.
const JS = new URL("../../src/test_junkie_tcms/web/js/", import.meta.url);
const ui = await import(new URL("ui.js", JS).href);
const data = await import(new URL("./fixtures/data.js", import.meta.url).href);
const { default: view, keyboard: kb } = await import(new URL("views/tree.js", JS).href);

const ctx = await data.context();
ui.configure(ctx);
const tree = async (state = "default") => (await data.load("tree", state)).tree;

/* a key pressed again and again from a row, following focus moves; toggles change the model like the live tree does */
async function press(from, keys) {
  const model = await tree();
  const out = [];
  let id = from;
  for (const key of keys) {
    const r = kb.navKey(model, id, key);
    if (r?.focus) id = r.focus;
    if (r?.toggle) {
      const x = kb.visible(model).find((v) => v.id === r.toggle);
      const walk = (xs) => xs.forEach((n) => { if (n.id === x.id) n.open = !n.open; else if (n.kids) walk(n.kids); });
      walk(model);
    }
    out.push({ key, result: r, focus: id });
  }
  return out;
}

/* walks the drop bar from src: every place a step at a time, as {id, z, why} */
function walkSlots(model, src, dir) {
  const sl = kb.slots(model, src), seen = [];
  let cur = null;
  for (;;) {
    const next = kb.stepSlot(sl, cur, dir);
    if (next === cur || next == null) break;
    cur = next;
    const s = sl.list[cur];
    seen.push({ ...s, why: kb.check(model, src, s.id, s.z) });
  }
  return seen;
}

const out = {};
out.visible = kb.visible(await tree()).map((r) => r.id);
out.nav = {
  down: await press("f-checkout", ["ArrowDown", "ArrowDown", "ArrowDown"]),
  homeEnd: await press("f-wallet", ["End", "Home", "ArrowUp"]),
  collapse: await press("f-card", ["ArrowLeft", "ArrowDown", "ArrowRight", "ArrowRight"]),
  leftFromCase: await press("c-PAY-118", ["ArrowLeft", "ArrowLeft"]),
  enterCase: await press("c-PAY-101", ["Enter", "ArrowRight", " "]),
  enterFeature: await press("f-wallet", ["Enter"]),
  missing: await press("nope", ["ArrowDown"]),
};

const model = await tree();
const sl = kb.slots(model, "c-PAY-140");
out.slots140 = { first: sl.list[kb.stepSlot(sl, null, 1)], second: sl.list[kb.stepSlot(sl, kb.stepSlot(sl, null, 1), 1)], up: sl.list[kb.stepSlot(sl, null, -1)] };
out.down140 = walkSlots(model, "c-PAY-140", 1);
out.up101 = walkSlots(model, "c-PAY-101", -1);
out.refusals = {
  caseAtRoot: kb.check(model, "c-PAY-101", "f-checkout", "before"),
  featureInOwnKid: kb.check(model, "f-checkout", "f-card", "in"),
  caseInWallet: kb.check(model, "c-PAY-140", "f-wallet", "in"),
};

/* where a keyboard move sends its write: the same place() drag uses, without the node it moves */
const where = ({ from, parent, position }) => ({ from, parent, position });

/* PAY-140 into f-wallet */
out.moveIn = where(kb.place("c-PAY-140", "f-wallet", "in", await tree()));

/* "after F" when open F is last in its list: with f-payouts gone, f-subs is open and last at the top */
const m2 = await tree();
m2.splice(m2.findIndex((x) => x.id === "f-payouts"), 1);
const sl2 = kb.slots(m2, "f-partial");
out.lastOpen = { after: sl2.list.findIndex((s) => s.id === "f-subs" && s.z === "after"), prorate: sl2.list.findIndex((s) => s.id === "f-prorate" && s.z === "after") };
out.lastOpen.placed = where(kb.place("f-partial", "f-subs", "after", m2));

/* one tab stop per tree state */
out.tabstops = {};
for (const state of Object.keys(view.states)) {
  const d = await data.load("tree", state);
  d.ctx = ctx;
  const html = view.states[state].render(d);
  out.tabstops[state] = { zero: (html.match(/tabindex="0" role="treeitem"/g) || []).length, rows: (html.match(/role="treeitem"/g) || []).length };
}
process.stdout.write(JSON.stringify(out));
