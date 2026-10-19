// T38 test harness: runs app/static/app.js in Node against a minimal fake DOM and prints the
// export and the print view as JSON. Used by test_shortlist_export.py; not shipped.
"use strict";
const fs = require("fs");
const path = require("path");

function makeEl(tag) {
  const e = {
    tagName: String(tag).toUpperCase(), children: [], attrs: {}, dataset: {}, style: {}, className: "",
    _text: null, value: "", checked: false, disabled: false, hidden: false, listeners: {},
    classList: {
      add(c) { const s = new Set(e.className.split(" ").filter(Boolean)); s.add(c); e.className = [...s].join(" "); },
      remove(c) { e.className = e.className.split(" ").filter(x => x && x !== c).join(" "); },
      toggle(c, on) { on ? e.classList.add(c) : e.classList.remove(c); },
      contains(c) { return e.className.split(" ").includes(c); },
    },
    appendChild(c) { e.children.push(c); c.parentNode = e; return c; },
    removeChild(c) { e.children = e.children.filter(x => x !== c); return c; },
    get firstChild() { return e.children[0] || null; },
    get childNodes() { return e.children; },
    set textContent(t) { e.children = []; e._text = t === null || t === undefined ? "" : String(t); },
    get textContent() { return (e._text || "") + e.children.map(c => c.textContent).join(""); },
    setAttribute(k, v) { e.attrs[k] = String(v); },
    getAttribute(k) { return e.attrs[k]; },
    addEventListener(t, f) { (e.listeners[t] = e.listeners[t] || []).push(f); },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    getBoundingClientRect() { return { top: 0, right: 0 }; },
    focus() {}, click() {},
  };
  return e;
}

const byId = {};
const document = {
  createElement: makeEl,
  createTextNode: t => { const n = makeEl("#text"); n._text = String(t); return n; },
  getElementById: id => (byId[id] = byId[id] || makeEl("div")),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  body: makeEl("body"),
};
let printed = 0;
const sandbox = { document, window: { print() { printed += 1; }, matchMedia: () => ({ matches: true }) },
                  fetch: () => Promise.resolve({ ok: false, json: () => ({}) }), URL, setTimeout, console, performance: { now: () => 0 },
                  Blob: function () {} };
const src = fs.readFileSync(path.join(__dirname, "..", "..", "app", "static", "app.js"), "utf8");
new Function(...Object.keys(sandbox), src + "\n;globalThis.__app = { setShortlist, exportData, buildPrintView, exportPdf, renderShortlist, shortlist: () => shortlist, setQuery: q => { lastQuery = q; } };")(...Object.values(sandbox));
const app = globalThis.__app;

// Input comes from a UTF-8 file: Windows command-line arguments mangle non-ASCII text.
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const result = input.result;
const note = input.note;
app.setQuery("CONFIDENTIAL company text: GlucoWear AG needs a needle-free sensor");
app.setShortlist(result, "select", null);
app.shortlist()[result.entity_id].note = note;
document.getElementById("sl-include-request").checked = process.argv[3] === "with-request";
// Jury round 3: Apertus' verdict travels with the entry and is exported only on opt-in.
app.shortlist()[result.entity_id].assessment = { entity_id: result.entity_id, category: "related_capability",
  explanation: "AI_TEXT_MARKER the project works on needle-free glucose sensing." };
document.getElementById("sl-include-ai").checked = process.argv[3] === "with-ai";
const data = app.exportData();
app.exportPdf();

// Collect what the shortlist entry offers for editing: every input/textarea and its type.
const entry = byId["sl-selected"].children[0];
const controls = [];
(function walk(n) { if (n.tagName === "INPUT" || n.tagName === "TEXTAREA") controls.push(n.tagName + ":" + (n.type || "")); n.children.forEach(walk); })(entry);

function dump(n) { return { tag: n.tagName, cls: n.className, text: n._text, children: n.children.map(dump) }; }
process.stdout.write(JSON.stringify({ data, printed, printView: dump(byId["print-view"]), printText: byId["print-view"].textContent, controls }));
