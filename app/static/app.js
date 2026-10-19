"use strict";
// All text is inserted with textContent: source text is data, never markup or instructions.
var revision = 0;

// T28 (interface half): the page speaks English, German or French. English text stays inline
// as t("key", "English"); i18n.js holds the German and French tables. Chosen by ?lang=, then the
// last choice in this browser, then the browser language. Apertus' own text is not translated.
var UI_LANGS = ["en", "de", "fr"];
var uiLang = "en";
var translated = {}; // shown text -> how it was made, so a status line can be re-translated

function t(key, en, vars) {
  var table = typeof I18N !== "undefined" && I18N[uiLang];
  var s = (table && table[key]) || en;
  if (vars) Object.keys(vars).forEach(function (k) { s = s.split("{" + k + "}").join(String(vars[k])); });
  translated[s] = { key: key, en: en, vars: vars };
  return s;
}

// A fixed English text from the server, translated when the table knows its exact wording.
function serverText(s) {
  var row = typeof SERVER_TEXT !== "undefined" && SERVER_TEXT[s];
  return (row && row[uiLang]) || s;
}

function pickLanguage() {
  var asked = null;
  try { asked = new URLSearchParams(window.location.search).get("lang"); } catch (e) { /* no URL here */ }
  if (!asked) try { asked = window.localStorage.getItem("bm-lang"); } catch (e) { /* storage blocked */ }
  if (!asked && typeof navigator !== "undefined" && navigator.language) asked = navigator.language.slice(0, 2);
  return UI_LANGS.indexOf(asked) >= 0 ? asked : "en";
}

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function dateLine(label, value) {
  return label + ": " + (value ? value : t("unknown", "unknown"));
}

var queryTerms = [];       // words of the current query, for highlighting evidence
var lastRequestId = null;
var lastRevision = 0;
var selectedType = "";
var shortlist = {};        // entity_id -> { name, state: "select" | "exclude" }
var feedbackCounter = 0;

var TYPE_NAMES = { person: "Person", unit: "Research group", project: "Project", infrastructure: "Lab / equipment", service: "Service" };
var FRESHNESS = { fresh: ["Recent source", "The source page was updated recently."],
                  stale: ["Older source", "The source page has not been updated for a while. Check that it is still current."] };
var TYPES = [["", "Anything"], ["person", "People"], ["unit", "Groups"], ["project", "Projects"],
             ["infrastructure", "Infrastructure"], ["service", "Services"]];
// Example queries in the page language. English keeps one per language, to show cross-language search.
// Each was run on the live index (19 Oct 2026) and finds the right pages.
var EXAMPLES = [["DE", "Messung des Blutzuckers ohne Nadel für eine Smartwatch"],
                ["EN", "glucose sensors"], ["FR", "robotique pour la rééducation"]];
var EXAMPLES_BY_LANG = {
  en: EXAMPLES,
  de: [["DE", "Messung des Blutzuckers ohne Nadel für eine Smartwatch"], ["DE", "Glukosesensoren für Diabetes"],
       ["DE", "Robotik für die Rehabilitation"]],
  fr: [["FR", "mesure du glucose sans aiguille pour une montre connectée"], ["FR", "mesure non invasive de la glycémie"],
       ["FR", "robotique pour la rééducation"]]
};

function renderExamples() {
  var ex = document.getElementById("examples");
  clearNode(ex);
  (EXAMPLES_BY_LANG[uiLang] || EXAMPLES).forEach(function (e) {
    var b = button("", function () { document.getElementById("query").value = e[1]; userNeeds = []; suggestedNeeds = []; runSearch([]); }, "example");
    b.appendChild(el("span", "lang", e[0]));
    b.appendChild(document.createTextNode(e[1]));
    ex.appendChild(b);
  });
}
var FIELD_LABELS = { role: "Role", affiliation: "Affiliation", part_of: "Part of", led_by: "Led by", leads: "Leads",
                     members: "Members", includes: "Includes", expertise: "Expertise", projects: "Projects",
                     infrastructure: "Infrastructure", services: "Services",
                     official_contact: "Official contact (role only, not expertise)",
                     contact: "Official contact (role only, not expertise)" };

function typeName(k) { return TYPE_NAMES[k] ? t("type." + k, TYPE_NAMES[k]) : k; }
function typeChip(tp) { return t("chip." + (tp[0] || "any"), tp[1]); }
function fieldLabel(k) { return t("field." + k, FIELD_LABELS[k]); }

// Suggestion chips: entity types and institutions are built here; other labels are server text.
function suggestionLabel(s) {
  if (s.kind === "entity_type") {
    var tp = TYPES.filter(function (x) { return x[0] === s.value; })[0];
    return tp ? typeChip(tp) : serverText(s.label);
  }
  if (s.kind === "institution" && s.value) return t("sugg.only", "Only {x}", { x: s.value });
  return serverText(s.label);
}

// Source tag from the evidence host. Unknown hosts are shown by hostname, never guessed.
function sourceOf(url) {
  var host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch (e) { return { key: "other", label: t("src.other", "Other") }; }
  if (host.indexOf("artorg") >= 0) return { key: "artorg", label: "ARTORG", full: t("src.artorg", "ARTORG Center") };
  if (host.indexOf("dbmr") >= 0 || host.indexOf("dcb") >= 0 || host.indexOf("diabetes") >= 0) return { key: "dcb", label: "DCB", full: t("src.dcb", "Diabetes Center Berne") };
  if (/(^|\.)unibe\.ch$/.test(host)) return { key: "unibe", label: "UniBE", full: t("src.unibe", "University of Bern") };
  return { key: "other", label: host || t("src.other", "Other") };
}

// Function words are not highlighted: marking every "der" or "the" in a quote hides the real match.
var STOP_WORDS = {};
("the and for with from that this are was our their into about " +
 "der die das den dem des und für mit von bei zur zum ein eine einer eines auf aus ist sind " +
 "les des une pour avec dans sur par aux est " +
 "per con del della delle degli che una nel nella").split(" ").forEach(function (w) { STOP_WORDS[w] = true; });

function termsOf(q) {
  var seen = {};
  return (q.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) || []).filter(function (w) {
    if (seen[w] || STOP_WORDS[w]) return false; seen[w] = true; return true;
  });
}

// Builds text nodes and <mark> elements only: source text is never parsed as markup.
function highlighted(parent, text, terms) {
  if (!terms.length) { parent.appendChild(document.createTextNode(text)); return parent; }
  var lower = text.toLowerCase(), pos = 0;
  var spans = [];
  terms.forEach(function (t) {
    var from = 0, i;
    while ((i = lower.indexOf(t, from)) >= 0) { spans.push([i, i + t.length]); from = i + t.length; }
  });
  spans.sort(function (a, b) { return a[0] - b[0] || b[1] - a[1]; });
  spans.forEach(function (s) {
    if (s[0] < pos) { if (s[1] <= pos) return; s = [pos, s[1]]; }
    if (s[0] > pos) parent.appendChild(document.createTextNode(text.slice(pos, s[0])));
    parent.appendChild(el("mark", null, text.slice(s[0], s[1])));
    pos = s[1];
  });
  if (pos < text.length) parent.appendChild(document.createTextNode(text.slice(pos)));
  return parent;
}

var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function shortDate(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? t("date.format", "{d} {m} {y}", { d: +m[3], m: t("month." + (+m[2]), MONTHS[+m[2] - 1]), y: m[1] }) : null;
}

// Short readable link text: host + path, trimmed. The full URL stays in the tooltip.
function shortUrl(url) {
  try {
    var u = new URL(url), s = u.hostname.replace(/^www\./, "") + u.pathname.replace(/\/$/, "");
    return s.length > 60 ? s.slice(0, 57) + "…" : s;
  } catch (e) { return url; }
}

function renderEvidence(ev) {
  var box = el("blockquote", "evidence");
  box.appendChild(highlighted(el("p", "quote"), ev.text, queryTerms));
  var meta = el("p", "meta");
  var a = el("a", "src", shortUrl(ev.url) + " ↗");
  // Only http(s) links are made clickable.
  if (/^https?:\/\//i.test(ev.url)) { a.href = ev.url; a.rel = "noopener noreferrer"; a.target = "_blank"; }
  a.title = ev.url;
  meta.appendChild(a);
  // One compact date line; the full set is in the tooltip so nothing is lost.
  var parts = [];
  if (ev.content_date) parts.push(t("ev.dated", "dated {d}", { d: shortDate(ev.content_date) }));
  if (ev.last_modified) parts.push(t("ev.modified", "modified {d}", { d: shortDate(ev.last_modified) }));
  if (ev.fetched_at) parts.push(t("ev.fetched", "fetched {d}", { d: shortDate(ev.fetched_at) }));
  if (ev.page_number) parts.push(t("ev.page", "page {n}", { n: ev.page_number }));
  var dates = el("span", null, parts.length ? " · " + parts.join(" · ") : "");
  dates.title = dateLine(t("date.content", "Source content date"), ev.content_date) + " | " + dateLine(t("date.modified", "Last modified"), ev.last_modified) + " | " + dateLine(t("date.fetched", "Fetched"), ev.fetched_at);
  meta.appendChild(dates);
  box.appendChild(meta);
  return box;
}

// Only fields that have supported values are shown; empty ones are simply left out.
function renderFields(fields, card) {
  var dl = el("dl", "fields");
  Object.keys(FIELD_LABELS).forEach(function (k) {
    var vals = (fields && fields[k]) || [];
    if (!vals.length) return;
    dl.appendChild(el("dt", null, fieldLabel(k)));
    var dd = el("dd");
    vals.forEach(function (v) { dd.appendChild(el("div", null, v.value)); });
    dl.appendChild(dd);
  });
  if (dl.childNodes.length) card.appendChild(dl);
}

function sendFeedback(r, action) {
  feedbackCounter += 1;
  if (!lastRequestId) return;
  fetch("/api/v1/feedback", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schema_version: "1", request_id: lastRequestId, revision: lastRevision, entity_id: r.entity_id,
                           action: action, idempotency_key: lastRequestId + ":" + r.entity_id + ":" + action + ":" + feedbackCounter })
  }).catch(function () { /* feedback is best effort; the shortlist still works locally */ });
}

// T38: the shortlist keeps the card payload as the server sent it. Analysts can reorder entries,
// hide fields and add notes; they cannot change source facts or quotes. Session only.
var slOrder = [];          // selected entity ids, in the analyst's order
var listNote = "";
var lastQuery = "";

function setShortlist(r, state, card) {
  var cur = shortlist[r.entity_id];
  if (cur && cur.state === state) { delete shortlist[r.entity_id]; }
  else {
    shortlist[r.entity_id] = { name: r.display_name, state: state, result: r,
                               note: cur ? cur.note : "", hidden: cur ? cur.hidden : {} };
    sendFeedback(r, state);
  }
  slOrder = slOrder.filter(function (id) { return shortlist[id] && shortlist[id].state === "select" && id !== r.entity_id; });
  if (shortlist[r.entity_id] && shortlist[r.entity_id].state === "select") slOrder.push(r.entity_id);
  if (card) refreshCardState(card, r.entity_id);
  renderShortlist();
}

function moveEntry(id, delta) {
  var i = slOrder.indexOf(id), j = i + delta;
  if (i < 0 || j < 0 || j >= slOrder.length) return;
  slOrder.splice(i, 1); slOrder.splice(j, 0, id);
  renderShortlist();
  var again = document.querySelector('#sl-selected [data-entity="' + id.replace(/"/g, "") + '"] .mv-' + (delta < 0 ? "up" : "down"));
  if (again) again.focus();
}

function removeEntry(id) {
  delete shortlist[id];
  slOrder = slOrder.filter(function (x) { return x !== id; });
  var c = document.querySelector('.card[data-entity="' + id.replace(/"/g, "") + '"]');
  if (c) refreshCardState(c, id);
  renderShortlist();
}

function supportedFields(r) {
  return Object.keys(FIELD_LABELS).filter(function (k) { return r.fields && r.fields[k] && r.fields[k].length; });
}

function renderEntry(id, pos) {
  var item = shortlist[id], r = item.result;
  var li = el("li", "sl-entry");
  li.dataset.entity = id;
  li.addEventListener("dragstart", function (ev) { ev.dataTransfer.setData("text/plain", id); li.classList.add("dragging"); });
  li.addEventListener("dragend", function () { li.classList.remove("dragging"); });
  li.addEventListener("dragover", function (ev) { ev.preventDefault(); });
  li.addEventListener("drop", function (ev) {
    ev.preventDefault();
    var from = ev.dataTransfer.getData("text/plain");
    if (!from || from === id || slOrder.indexOf(from) < 0) return;
    slOrder.splice(slOrder.indexOf(from), 1);
    slOrder.splice(slOrder.indexOf(id), 0, from);
    renderShortlist();
  });
  var head = el("div", "sl-head");
  head.draggable = true; // only the title row drags, so the note box stays selectable
  head.appendChild(el("span", "sl-name", (pos + 1) + ". " + item.name));
  var up = button("↑", function () { moveEntry(id, -1); }); up.classList.add("mv-up"); up.setAttribute("aria-label", t("sl.up", "Move {name} up", { name: item.name })); up.disabled = pos === 0;
  var down = button("↓", function () { moveEntry(id, 1); }); down.classList.add("mv-down"); down.setAttribute("aria-label", t("sl.down", "Move {name} down", { name: item.name })); down.disabled = pos === slOrder.length - 1;
  head.appendChild(up); head.appendChild(down);
  head.appendChild(button(t("remove", "Remove"), function () { removeEntry(id); }));
  li.appendChild(head);
  var fields = supportedFields(r);
  if (fields.length) {
    var fs = el("div", "sl-fields");
    fs.appendChild(el("span", "meta", t("sl.showInExport", "Show in export:") + " "));
    fields.forEach(function (k) {
      var lab = el("label", "inline");
      var cb = el("input"); cb.type = "checkbox"; cb.checked = !item.hidden[k];
      cb.setAttribute("aria-label", t("sl.showField", "Show {field} of {name} in the export", { field: fieldLabel(k).split(" (")[0], name: item.name }));
      cb.addEventListener("change", function () { if (cb.checked) delete item.hidden[k]; else item.hidden[k] = true; });
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + fieldLabel(k).split(" (")[0]));
      fs.appendChild(lab);
    });
    li.appendChild(fs);
  }
  var nl = el("label", "sl-note-label", t("sl.note", "Analyst note (your text, not a source fact)"));
  var note = el("textarea", "sl-note"); note.rows = 2; note.maxLength = 1000; note.value = item.note;
  note.setAttribute("aria-label", t("sl.noteFor", "Analyst note for {name} (your text, not a source fact)", { name: item.name }));
  note.addEventListener("input", function () { item.note = note.value; });
  nl.appendChild(note);
  li.appendChild(nl);
  return li;
}

function refreshCardState(card, id) {
  var st = shortlist[id] ? shortlist[id].state : "";
  card.classList.toggle("excluded", st === "exclude");
  var sel = card.querySelector(".act-select"), exc = card.querySelector(".act-exclude");
  if (sel) sel.setAttribute("aria-pressed", String(st === "select"));
  if (exc) exc.setAttribute("aria-pressed", String(st === "exclude"));
}

function renderShortlist() {
  var sel = document.getElementById("sl-selected"), exc = document.getElementById("sl-excluded");
  clearNode(sel); clearNode(exc);
  slOrder.forEach(function (id, i) { sel.appendChild(renderEntry(id, i)); });
  if (!sel.firstChild) sel.appendChild(el("li", "none", t("sl.emptySelected", "Nothing yet. Use Select on a result card.")));
  Object.keys(shortlist).forEach(function (id) {
    if (shortlist[id].state !== "exclude") return;
    var li = el("li");
    li.appendChild(el("span", null, shortlist[id].name));
    li.appendChild(button(t("remove", "Remove"), function () { removeEntry(id); }));
    exc.appendChild(li);
  });
  if (!exc.firstChild) exc.appendChild(el("li", "none", t("sl.emptyExcluded", "Nothing yet")));
  document.getElementById("shortlist-count").textContent = String(slOrder.length);
  document.getElementById("sl-export").disabled = !slOrder.length;
  document.getElementById("sl-json").disabled = !slOrder.length;
}

// Built from the stored card payload only: names, supported fields, exact quotes, URLs, dates.
// AI-generated assessments are never included. The request text only with the analyst's opt-in.
function exportData() {
  var withRequest = document.getElementById("sl-include-request").checked;
  var fetched = [];
  var entries = slOrder.map(function (id) {
    var item = shortlist[id], r = item.result;
    var fields = {};
    supportedFields(r).forEach(function (k) { if (!item.hidden[k]) fields[k] = r.fields[k].map(function (v) { return v.value; }); });
    var quotes = r.evidence.slice(0, 2).map(function (e) {
      if (e.fetched_at) fetched.push(e.fetched_at);
      return { text: e.text, url: e.url, content_date: e.content_date, last_modified: e.last_modified, fetched_at: e.fetched_at };
    });
    return { entity_id: r.entity_id, name: r.display_name, type: r.entity_type, source: sourceOf(r.evidence[0].url).label,
             fields: fields, evidence: quotes, analyst_note: item.note.trim() || null };
  });
  fetched.sort();
  return { title: t("pv.title", "Bern Match shortlist"), exported_at: new Date().toISOString(), request: withRequest ? lastQuery : null,
           analyst_note: listNote.trim() || null, fetched_from: fetched[0] || null, fetched_to: fetched[fetched.length - 1] || null,
           entries: entries };
}

function buildPrintView(data) {
  var view = document.getElementById("print-view");
  clearNode(view);
  view.appendChild(el("h1", null, data.title));
  view.appendChild(el("p", "meta", t("pv.exported", "Exported {when} UTC", { when: data.exported_at.slice(0, 16).replace("T", " ") }) + " · " +
    t(data.entries.length === 1 ? "pv.entry" : "pv.entries", data.entries.length === 1 ? "{n} entry" : "{n} entries", { n: data.entries.length }) +
    (data.fetched_from ? " · " + t("pv.fetched", "source pages fetched {from}", { from: data.fetched_from.slice(0, 10) }) + (data.fetched_to.slice(0, 10) !== data.fetched_from.slice(0, 10) ? " " + t("pv.to", "to {to}", { to: data.fetched_to.slice(0, 10) }) : "") : "")));
  if (data.request) view.appendChild(el("p", null, t("pv.request", "Request:") + " " + data.request));
  if (data.analyst_note) {
    var ln = el("section", "pv-note");
    ln.appendChild(el("h3", null, t("pv.listNote", "Analyst note for this list (not a source fact)")));
    ln.appendChild(el("p", null, data.analyst_note));
    view.appendChild(ln);
  }
  data.entries.forEach(function (e, i) {
    var s = el("section", "pv-entry");
    s.appendChild(el("h2", null, (i + 1) + ". " + e.name));
    s.appendChild(el("p", "meta", typeName(e.type) + " · " + e.source));
    var keys = Object.keys(e.fields);
    if (keys.length) {
      var dl = el("dl", "fields");
      keys.forEach(function (k) {
        dl.appendChild(el("dt", null, fieldLabel(k)));
        var dd = el("dd"); e.fields[k].forEach(function (v) { dd.appendChild(el("div", null, v)); }); dl.appendChild(dd);
      });
      s.appendChild(dl);
    }
    e.evidence.forEach(function (q) {
      var b = el("blockquote", "evidence");
      b.appendChild(el("p", "quote", q.text));
      b.appendChild(el("p", "meta", q.url));
      b.appendChild(el("p", "meta", dateLine(t("date.content", "Source content date"), q.content_date) + " | " + dateLine(t("date.modified", "Last modified"), q.last_modified) + " | " + dateLine(t("date.fetched", "Fetched"), q.fetched_at)));
      s.appendChild(b);
    });
    if (e.analyst_note) {
      var n = el("div", "pv-note");
      n.appendChild(el("h3", null, t("pv.note", "Analyst note (not a source fact)")));
      n.appendChild(el("p", null, e.analyst_note));
      s.appendChild(n);
    }
    view.appendChild(s);
  });
  view.appendChild(el("p", "meta pv-footer", t("pv.footer", "Facts and quotes come from the public pages named under each quote, as stored in the Bern Match index on the fetch dates shown. " +
    "Analyst notes are the analyst's own text and are not source facts. No AI-generated text is included.")));
}

function exportPdf() {
  if (!slOrder.length) return;
  buildPrintView(exportData());
  window.print(); // the browser's print dialog saves it as PDF; nothing is sent to the server
}

function exportJson() {
  if (!slOrder.length) return;
  var blob = new Blob([JSON.stringify(exportData(), null, 2)], { type: "application/json" });
  var a = el("a"); a.href = URL.createObjectURL(blob); a.download = "bern-match-shortlist.json";
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
}

var LANG_NAMES = { en: "English", de: "German", fr: "French", it: "Italian", ru: "Russian" };

function langName(code) { return LANG_NAMES[code] ? t("lang." + code, LANG_NAMES[code]) : (code ? String(code).toUpperCase() : t("unknown", "unknown")); }

// The server's language guess on short queries is sometimes wrong (an English query shown as
// Italian). When it disagrees with the simple check below, the page shows the simple check.
function requestLang(serverCode) {
  if (!lastQuery) return serverCode;
  var guess = guessLanguage(lastQuery).toLowerCase();
  return serverCode && String(serverCode).toLowerCase() === guess ? serverCode : guess;
}

// "Why this result?" (T36 data): only retrieval signals the server measured, no model text.
// Written for analysts: plain reasons, no ranks or scores.
function renderWhy(r) {
  var sig = r.retrieval || {};
  var box = el("details", "why");
  box.appendChild(el("summary", null, t("why.title", "Why this result?")));
  var ul = el("ul", "why-list");
  function line(text) { ul.appendChild(el("li", null, text)); }
  if (sig.matched_terms && sig.matched_terms.length) {
    var li = el("li", null, t("why.words", "The source uses your words:") + " ");
    sig.matched_terms.forEach(function (w) { li.appendChild(el("span", "badge", w)); li.appendChild(document.createTextNode(" ")); });
    ul.appendChild(li);
  } else if (sig.keyword_rank) {
    line(t("why.someWords", "The source uses words from your request."));
  }
  if (sig.dense_rank) line(t("why.topic", "The source talks about the same topic, even where the wording differs."));
  var ql = requestLang(sig.query_language);
  if (ql && sig.evidence_language && ql !== sig.evidence_language)
    line(t("why.lang", "Found across languages: you wrote in {q}, the source is in {e}.", { q: langName(ql), e: langName(sig.evidence_language) }));
  if (sig.query_variant === "expansion" && sig.query_variants && sig.query_variants.length)
    line(t("why.apertus", "Found with a wording Apertus suggested: {w}.", { w: sig.query_variants.join(", ") }));
  if (sig.demoted_listing_page) line(t("why.listing", "Shown lower because the page looks like a list, news or report page."));
  if (!ul.firstChild) return null;
  box.appendChild(ul);
  box.appendChild(el("p", "meta", t("why.footer", "Worked out by the search engine from the source text. Not a probability and not AI-generated.")));
  return box;
}

var QUOTES_SHOWN = 2;

function renderCard(r, index) {
  var src = sourceOf(r.evidence[0].url);
  var card = el("article", "card appear src-" + src.key);
  card.style.animationDelay = Math.min(index || 0, 10) * 60 + "ms";
  card.dataset.entity = r.entity_id;
  // Same host form as the server's "Only <host>" suggestion (lower case, no "www.").
  try { card.dataset.host = new URL(r.evidence[0].url).hostname.toLowerCase().replace(/^www\./, ""); } catch (e) { card.dataset.host = ""; }
  var head = el("div", "card-head");
  var title = el("h3");
  title.appendChild(el("span", "rank", r.rank + "."));
  title.appendChild(document.createTextNode(r.display_name));
  head.appendChild(title);
  var actions = el("div", "actions");
  var sel = button(t("card.select", "Select"), function () { setShortlist(r, "select", card); }); sel.classList.add("act-select");
  var exc = button(t("card.exclude", "Exclude"), function () { setShortlist(r, "exclude", card); }); exc.classList.add("act-exclude");
  sel.setAttribute("aria-pressed", "false"); exc.setAttribute("aria-pressed", "false");
  actions.appendChild(sel); actions.appendChild(exc);
  head.appendChild(actions);
  card.appendChild(head);
  // Badges in plain words; anything we cannot say clearly is not shown.
  var tags = el("div", "tags");
  var srcTag = el("span", "badge tag-" + src.key, src.full || src.label);
  srcTag.title = t("card.srcTitle", "Where this comes from");
  tags.appendChild(srcTag);
  if (TYPE_NAMES[r.entity_type]) tags.appendChild(el("span", "badge", typeName(r.entity_type)));
  if (FRESHNESS[r.freshness]) {
    var fr = el("span", "badge fresh-" + r.freshness, t("fresh." + r.freshness, FRESHNESS[r.freshness][0]));
    fr.title = t("fresh." + r.freshness + ".title", FRESHNESS[r.freshness][1]);
    tags.appendChild(fr);
  }
  var rt = r.retrieval || {};
  var ql = requestLang(rt.query_language);
  if (ql && rt.evidence_language && ql !== rt.evidence_language && LANG_NAMES[rt.evidence_language]) {
    var lt = el("span", "badge lang", t("card.srcIn", "Source in {lang}", { lang: langName(rt.evidence_language) }));
    lt.title = t("card.srcInTitle", "Found across languages: your request is in {q}, the source page is in {e}.", { q: langName(ql), e: langName(rt.evidence_language) });
    tags.appendChild(lt);
  }
  card.appendChild(tags);
  var why = renderWhy(r);
  renderFields(r.fields, card);
  // The best quotes first; the rest fold away so one card never fills the screen.
  r.evidence.slice(0, QUOTES_SHOWN).forEach(function (ev) { card.appendChild(renderEvidence(ev)); });
  if (r.evidence.length > QUOTES_SHOWN) {
    var more = el("details", "more-quotes");
    var n = r.evidence.length - QUOTES_SHOWN;
    more.appendChild(el("summary", null, t(n === 1 ? "card.moreQuote" : "card.moreQuotes", n === 1 ? "Show {n} more quote" : "Show {n} more quotes", { n: n })));
    r.evidence.slice(QUOTES_SHOWN).forEach(function (ev) { more.appendChild(renderEvidence(ev)); });
    card.appendChild(more);
  }
  if (why) card.appendChild(why);
  refreshCardState(card, r.entity_id);
  return card;
}

// T30 reranked event: cards slide from their old place to the new one; new and moved cards are marked.
function rerankCards(results) {
  shownResults = results; shownMode = "apertus"; // ranks before were the direct ones, as in baseRanks
  var out = document.getElementById("results");
  var before = {}, oldRank = {};
  Array.prototype.forEach.call(out.querySelectorAll(".card"), function (c, i) {
    before[c.dataset.entity] = c.getBoundingClientRect().top; oldRank[c.dataset.entity] = i + 1;
  });
  clearNode(out);
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  results.forEach(function (r, i) {
    var card = renderCard(r, 0);
    card.classList.remove("appear");
    var was = oldRank[r.entity_id];
    var note = !was ? t("ap.found", "Found by Apertus") : was > r.rank ? t("ap.up", "Moved up by Apertus (was #{n})", { n: was }) : was < r.rank ? t("ap.down", "Moved down by Apertus (was #{n})", { n: was }) : "";
    if (note) { card.classList.add("moved"); card.querySelector(".tags").appendChild(el("span", "badge moved-badge", note)); }
    out.appendChild(card);
    if (still) return;
    var top = card.getBoundingClientRect().top;
    if (was && card.animate) card.animate([{ transform: "translateY(" + (before[r.entity_id] - top) + "px)" }, { transform: "none" }], { duration: 450, easing: "ease-out" });
    else if (card.animate) card.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 400, delay: i * 40, easing: "ease-out", fill: "backwards" });
  });
}

function renderCards(results) {
  var out = clearResults();
  results.forEach(function (r, i) { out.appendChild(renderCard(r, i)); });
}

function setStatus(text, kind) {
  var s = document.getElementById("status");
  s.textContent = text;
  s.className = "status " + (kind || "");
  lastStatus = { text: text, kind: kind };
}

function clearResults() {
  var out = document.getElementById("results");
  while (out.firstChild) out.removeChild(out.firstChild);
  return out;
}

function showSkeletons() {
  var out = clearResults();
  for (var i = 0; i < 3; i++) { var s = el("div", "skeleton"); s.setAttribute("aria-hidden", "true"); out.appendChild(s); }
}

// Heuristic only (stop words and diacritics); shown as "detected", never as a fact about the evidence.
function guessLanguage(q) {
  var s = " " + q.toLowerCase() + " ";
  if (/[Ѐ-ӿ]/.test(s)) return "RU";
  if (/ (der|die|das|und|für|mit|von|zur|bei|in der) |[äöüß]/.test(s)) return "DE";
  if (/ (le|la|les|des|pour|avec|et|du|de la) |[àâçèéêëîïôùû]/.test(s)) return "FR";
  if (/ (il|lo|gli|per|con|della|delle|e) /.test(s)) return "IT";
  return "EN";
}

function renderSummary(b, query, elapsedMs, byApertus) {
  lastSummary = [b, query, elapsedMs, byApertus];
  var box = document.getElementById("summary");
  clearNode(box);
  box.hidden = false;
  var total = b.timing_ms && typeof b.timing_ms.request_total === "number" ? b.timing_ms.request_total : elapsedMs;
  var count = t(b.results.length === 1 ? "sum.result" : "sum.results", b.results.length === 1 ? "{n} result" : "{n} results", { n: b.results.length });
  box.appendChild(el("span", "pill latency", byApertus ? t("sum.byApertus", "{count}, ranked by Apertus in {s} s", { count: count, s: (elapsedMs / 1000).toFixed(1) })
                                                       : t("sum.direct", "{count} in {ms} ms", { count: count, ms: Math.round(total) })));
  var first = b.results[0] && b.results[0].retrieval;
  var ql = first && first.query_language && requestLang(first.query_language);
  if (ql) {
    var cross = b.results.filter(function (r) { var t = r.retrieval || {}; return t.evidence_language && t.evidence_language !== ql; }).length;
    box.appendChild(el("span", "pill", t("sum.request", "{lang} request", { lang: langName(ql) }) + (cross ? " · " + t(cross === 1 ? "sum.cross1" : "sum.cross", cross === 1 ? "{n} card with evidence in another language" : "{n} cards with evidence in another language", { n: cross }) : "")));
  } else {
    var guessed = guessLanguage(query);
    if (guessed !== "EN") box.appendChild(el("span", "pill", t("sum.detected", "Query language detected: {lang} (evidence may be in another language)", { lang: guessed })));
  }
}

var OUTCOME_TEXT = {
  low_confidence: ["Low confidence", "These results are weak matches. Check the quotes before relying on them."],
  too_broad: ["Request is too broad", "Many things match. Narrow it down with one of the options below."],
  no_evidence: ["Nothing found", "The indexed corpus has no supported evidence for this request."]
};

function renderOutcome(b, byApertus) {
  var box = document.getElementById("outcome");
  clearNode(box);
  var info = OUTCOME_TEXT[b.outcome] && [t("out." + b.outcome, OUTCOME_TEXT[b.outcome][0]), t("out." + b.outcome + ".text", OUTCOME_TEXT[b.outcome][1])];
  // The outcome was measured on the direct search. Over Apertus' ranking, say exactly that.
  if (byApertus && b.outcome === "low_confidence")
    info = [t("out.weakWording", "Weak match on your exact wording"), t("out.weakWording.text", "The direct search found only weak matches, so Apertus widened it with other wordings. Check the quotes before relying on a result.")];
  // Apertus checked the cards and found none that clearly matches: that comes first.
  if (noClearMatch)
    info = [t("out.noClear", "No clear match"), t("out.noClear.text", "Apertus rated none of these cards a clear match. They are the closest pages found. Check the quotes before using any of them.")];
  if (!info) { box.hidden = true; return; }
  box.hidden = false;
  box.appendChild(el("h2", null, info[0]));
  box.appendChild(el("p", null, info[1]));
  var chips = el("div", "chips");
  var notes = [];
  (b.suggestions || []).forEach(function (s) {
    if (s.kind === "coverage") { notes.push(serverText(s.label)); return; } // information, not an action
    chips.appendChild(button(suggestionLabel(s), function () { applySuggestion(s, box); }, "chip"));
  });
  if (chips.firstChild) box.appendChild(chips);
  notes.forEach(function (n) { box.appendChild(el("p", "meta", n)); });
}

// A fresh search with new request text, as if the analyst had typed it and pressed Search.
function rerunWith(text) {
  document.getElementById("query").value = text;
  userNeeds = []; suggestedNeeds = []; refineOpen = false;
  runSearch([]);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// A small inline box: type, press Enter or the button, and the search runs again.
function inlineAsk(container, placeholder, initial, buttonLabel, onSubmit, focus) {
  var old = container.querySelector(".ask");
  if (old) old.parentNode.removeChild(old);
  var form = el("form", "ask");
  var input = el("input"); input.type = "text"; input.maxLength = 300; input.placeholder = placeholder; input.value = initial || "";
  input.setAttribute("aria-label", placeholder);
  form.appendChild(input);
  var go = el("button", "primary", buttonLabel); go.type = "submit";
  form.appendChild(go);
  form.appendChild(button(t("cancel", "Cancel"), function () { container.removeChild(form); }));
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var v = input.value.trim();
    if (v) onSubmit(v);
  });
  container.appendChild(form);
  if (focus !== false) input.focus(); // only when the analyst opened the box themselves
  return form;
}

function addToRequest(extra) {
  var q = document.getElementById("query").value.trim();
  rerunWith(q ? q + ", " + extra : extra);
}

function filterInstitution(host, label) {
  var shown = 0;
  Array.prototype.forEach.call(document.querySelectorAll("#results .card"), function (c) {
    var on = !host || c.dataset.host === host;
    c.hidden = !on; if (on) shown += 1;
  });
  var status = document.getElementById("status");
  if (!host) { setStatus("", ""); return; }
  setStatus(t(shown === 1 ? "filter.one" : "filter.many", shown === 1 ? "Showing {n} result from {inst}." : "Showing {n} results from {inst}.", { n: shown, inst: label }), "");
  status.appendChild(document.createTextNode(" "));
  status.appendChild(button(t("filter.all", "Show all"), function () { filterInstitution(null); }));
}

function applySuggestion(s, box) {
  if (s.kind === "entity_type") { setType(s.value || ""); runSearch([]); }
  else if (s.kind === "institution" && s.value) filterInstitution(s.value, s.label.replace(/^Only /, ""));
  else if (s.kind === "rephrase" && s.value) rerunWith(s.value);
  else if (s.kind === "rephrase") {
    // "Add ..." / "Describe ..." add to the request; anything else rewrites it.
    var adds = /^(add|describe)\b/i.test(s.label);
    inlineAsk(box, adds ? t("ask.addPh", "e.g. a method, disease, technology or product") : t("ask.rewritePh", "Rewrite your request"),
              adds ? "" : document.getElementById("query").value.trim(),
              adds ? t("ask.add", "Add and search") : t("ask.again", "Search again"),
              adds ? addToRequest : rerunWith);
  }
}

function setType(value) {
  selectedType = value;
  var chips = document.querySelectorAll("#type-chips .chip");
  for (var i = 0; i < chips.length; i++) chips[i].setAttribute("aria-checked", String(chips[i].dataset.value === value));
}

// What is on screen now, so a language switch can redraw it without searching again.
var shownResults = null, shownMode = "direct", assessShown = {};
// What Apertus said about the request as a whole (jury round 1).
var noNeed = false;       // Apertus found no research need: its card verdicts are not shown
var assessFailed = false; // only the assessment stage failed; interpretation and ranking still stand
var noClearMatch = false; // every card Apertus checked came back "insufficient evidence"
var lastSummary = null, lastNotes = null, lastNeedsPayload = null, lastNeedNote = null, lastStatus = null;

// The static page: every element tagged data-i18n* in index.html (English kept as the default).
function applyStatic() {
  if (document.documentElement) document.documentElement.lang = uiLang;
  function each(attr, fn) {
    Array.prototype.forEach.call(document.querySelectorAll("[" + attr + "]"), function (n) {
      var store = "en" + attr.replace(/^data-i18n/, "").replace(/-/g, "");
      if (n.dataset[store] === undefined) n.dataset[store] = attr === "data-i18n" ? n.textContent : n.getAttribute(attr === "data-i18n-aria" ? "aria-label" : attr.replace("data-i18n-", ""));
      fn(n, t(n.getAttribute(attr), n.dataset[store]));
    });
  }
  each("data-i18n", function (n, s) { n.textContent = s; });
  each("data-i18n-placeholder", function (n, s) { n.setAttribute("placeholder", s); });
  each("data-i18n-title", function (n, s) { n.setAttribute("title", s); });
  each("data-i18n-aria", function (n, s) { n.setAttribute("aria-label", s); });
  Array.prototype.forEach.call(document.querySelectorAll("#type-chips .chip"), function (c) {
    var tp = TYPES.filter(function (x) { return x[0] === c.dataset.value; })[0];
    if (tp) c.textContent = typeChip(tp);
  });
  Array.prototype.forEach.call(document.querySelectorAll(".langs [data-lang]"), function (b) {
    b.setAttribute("aria-pressed", String(b.dataset.lang === uiLang));
  });
  renderExamples();
}

// Same text in the new language, if this page made it with t(); otherwise unchanged.
function retranslate(text) {
  var m = text && translated[text];
  return m ? t(m.key, m.en, m.vars) : text;
}

function setLanguage(code) {
  if (UI_LANGS.indexOf(code) < 0 || code === uiLang) return;
  uiLang = code;
  try { window.localStorage.setItem("bm-lang", code); } catch (e) { /* storage blocked: choice lasts this page only */ }
  var oldStatus = lastStatus;
  applyStatic();
  renderShortlist();
  if (!resultsShown) waitForApertus();
  else if (shownResults) {
    if (shownMode === "apertus") showApertusResults(shownResults); else renderCards(shownResults);
    Object.keys(assessShown).forEach(function (id) { renderAssessment(assessShown[id]); });
  }
  if (lastSummary) renderSummary.apply(null, lastSummary);
  if (lastNotes) renderNotes.apply(null, lastNotes);
  if (lastNeedsPayload) renderNeeds(lastNeedsPayload);
  else if (lastNeedNote) needNote(retranslate(lastNeedNote));
  if (resultsShown && oldStatus && oldStatus.text) setStatus(retranslate(oldStatus.text), oldStatus.kind);
}

function initHero() {
  uiLang = pickLanguage();
  Array.prototype.forEach.call(document.querySelectorAll(".langs [data-lang]"), function (b) {
    b.addEventListener("click", function () { setLanguage(b.dataset.lang); });
  });
  var group = document.getElementById("type-chips");
  TYPES.forEach(function (tp) {
    var c = button(typeChip(tp), function () { setType(tp[0]); }, "chip");
    c.dataset.value = tp[0]; c.setAttribute("role", "radio");
    group.appendChild(c);
  });
  setType("");
  var toggle = document.getElementById("shortlist-toggle"), drawer = document.getElementById("shortlist");
  toggle.addEventListener("click", function () {
    drawer.hidden = !drawer.hidden;
    toggle.setAttribute("aria-expanded", String(!drawer.hidden));
  });
  document.getElementById("shortlist-close").addEventListener("click", function () {
    drawer.hidden = true; toggle.setAttribute("aria-expanded", "false"); toggle.focus();
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && !drawer.hidden) { drawer.hidden = true; toggle.setAttribute("aria-expanded", "false"); toggle.focus(); }
  });
  var ln = document.getElementById("sl-list-note");
  ln.addEventListener("input", function () { listNote = ln.value; });
  document.getElementById("sl-export").addEventListener("click", exportPdf);
  document.getElementById("sl-json").addEventListener("click", exportJson);
  applyStatic();
  renderShortlist();
}

var eventSource = null;
var userNeeds = [];      // needs the analyst controls (origin "user")
var suggestedNeeds = []; // model suggestions: never sent as requirements until accepted
var needCounter = 0;
var needText = {};       // need_id -> text, so assessments name the need instead of its id

function closeEvents() {
  if (eventSource) { eventSource.close(); eventSource = null; }
}

function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function aiHead(text) {
  var h = el("p", "ai-head");
  h.appendChild(el("span", "ai-tag", t("ai.tag", "AI · Apertus")));
  h.appendChild(document.createTextNode(text));
  return h;
}

function needNote(text) {
  lastNeedNote = text; lastNeedsPayload = null;
  var box = document.getElementById("needs");
  clearNode(box);
  box.hidden = false;
  var busy = /^Interpreting/.test(text);
  box.appendChild(aiHead(busy ? t("ai.working", "Working on your request") : "Apertus"));
  box.appendChild(el("p", "meta" + (busy ? " busy" : ""),
    busy ? t("ai.reading", "Reading your request and searching the terms researchers use: synonyms, technical terms, other languages.") : text));
}

var refineOpen = false; // keep "Refine" open while the analyst edits needs

// Apertus' clarifying question, answerable in one click: its "e.g." options become chips,
// and a box takes any other answer. Either one is added to the request and the search runs again.
function renderClarification(text) {
  var wrap = el("div", "clarify");
  var m = /\s*\((?:e\.g\.|z\.\s?B\.|p\.\s?ex\.)[,:]?\s*([^)]*)\)/i.exec(text);
  var question = m ? text.replace(m[0], "") : text;
  wrap.appendChild(el("p", "reason", t("ai.focus", "To focus the search:") + " " + question.trim()));
  if (m) {
    var chips = el("div", "chips");
    m[1].split(/,|;|\bor\b|\boder\b|\bou\b/).map(function (s) { return s.trim(); })
      .filter(function (s) { return s && !/^(etc|usw|usw\.|etc\.)\.?$/i.test(s) && s.length <= 60; })
      .forEach(function (opt) { chips.appendChild(button(opt, function () { addToRequest(opt); }, "chip")); });
    if (chips.firstChild) wrap.appendChild(chips);
  }
  var ask = inlineAsk(wrap, t("ai.answerPh", "Or type your answer"), "", t("ask.add", "Add and search"), addToRequest, false);
  var cancel = ask.querySelector("button.small");
  if (cancel) cancel.hidden = true; // no Cancel: the box is part of the question
  return wrap;
}

function button(label, onclick, cls) {
  var b = el("button", cls || "small", label);
  b.type = "button";
  b.addEventListener("click", onclick);
  return b;
}

function renderNeeds(payload) {
  lastNeedsPayload = payload; lastNeedNote = null;
  var box = document.getElementById("needs");
  clearNode(box);
  box.hidden = false;
  box.appendChild(aiHead(t("ai.read", "How Apertus read your request")));
  if (payload.synthetic || payload.decoding_mode === "synthetic") box.appendChild(el("p", "synthetic", "SYNTHETIC fixture interpretation: not a real model output."));
  // The headline: the other wordings Apertus searched, so different terms still find the experts.
  if (payload.expanded_queries && payload.expanded_queries.length) {
    box.appendChild(el("p", "meta", t("ai.also", "Also searched as (the terms researchers use; added to the search, never to your requirements):")));
    var also = el("div", "also");
    payload.expanded_queries.forEach(function (q) {
      var chip = el("span", "wording");
      chip.appendChild(el("span", "lang", q.language));
      chip.appendChild(document.createTextNode(q.text));
      chip.title = t("ai.expands", "expands:") + " " + q.source;
      also.appendChild(chip);
    });
    box.appendChild(also);
  }
  var clar = String(payload.clarification || "").trim();
  if (clar && !/^(null|none|n\/a)$/i.test(clar)) box.appendChild(renderClarification(clar)); // the model sometimes writes "null"
  if (noNeed) box.appendChild(el("p", "meta", t("ai.noNeed", "Apertus found no research need in this request, so its verdicts on the cards are not shown.")));
  if (assessFailed) box.appendChild(el("p", "meta", t("ai.assessFail", "Apertus could not finish its card assessments this time.")));
  var refine = el("details", "refine");
  refine.open = refineOpen;
  refine.addEventListener("toggle", function () { refineOpen = refine.open; });
  refine.appendChild(el("summary", null, t("ai.refine", "Refine what the company needs ({n})", { n: userNeeds.length })));
  box.appendChild(refine);
  box = refine; // the editing tools live inside "Refine"
  box.appendChild(el("h3", null, t("ai.needs", "Your needs (editable)")));
  var list = el("ul", "needlist");
  userNeeds.forEach(function (n, i) {
    var li = el("li");
    var input = el("input");
    input.type = "text"; input.value = n.text; input.maxLength = 300;
    input.addEventListener("input", function () { n.text = input.value; });
    li.appendChild(input);
    li.appendChild(el("span", "badge", t("kind." + n.kind, n.kind)));
    li.appendChild(button(t("remove", "Remove"), function () { userNeeds.splice(i, 1); renderNeeds(payload); }));
    list.appendChild(li);
  });
  box.appendChild(list);
  if (suggestedNeeds.length) {
    box.appendChild(el("h3", null, t("ai.suggested", "Suggested by the model (not used until you accept)")));
    var sl = el("ul", "needlist suggested");
    suggestedNeeds.forEach(function (n, i) {
      var li = el("li");
      li.appendChild(el("span", null, n.text));
      li.appendChild(el("span", "badge", t("kind." + n.kind, n.kind)));
      li.appendChild(button(t("ai.accept", "Accept"), function () {
        suggestedNeeds.splice(i, 1);
        needCounter += 1;
        userNeeds.push({ schema_version: "1", need_id: "u" + needCounter, text: n.text, origin: "user", kind: n.kind });
        renderNeeds(payload);
      }));
      li.appendChild(button(t("ai.dismiss", "Dismiss"), function () { suggestedNeeds.splice(i, 1); renderNeeds(payload); }));
      sl.appendChild(li);
    });
    box.appendChild(sl);
  }
  var add = el("input"); add.type = "text"; add.placeholder = t("ai.addNeedPh", "Add a need"); add.maxLength = 300; add.id = "newneed";
  box.appendChild(add);
  box.appendChild(button(t("ai.add", "Add"), function () { addNeed(add.value, payload); }));
  box.appendChild(button(t("ai.rerun", "Re-run search with these needs"), function () { runSearch(userNeeds); }, ""));
}

function addNeed(text, payload) {
  text = (text || "").trim();
  if (!text || userNeeds.length >= 10) return;
  needCounter += 1;
  userNeeds.push({ schema_version: "1", need_id: "u" + needCounter, text: text, origin: "user", kind: "problem" });
  renderNeeds(payload);
}

var CATEGORY_LABELS = { direct_match: "Direct match", related_capability: "Related capability",
                        insufficient_evidence: "Insufficient evidence" };
var SUPPORT_LABELS = { supported: "supported", partial: "partly supported", none: "not supported" };

function renderAssessment(a) {
  if (noNeed) return; // a verdict without a recognised need can be badly wrong (jury round 1, q09)
  if (!resultsShown) { pendingAssess.push(a); return; } // shown with the cards once they appear
  var card = document.querySelector('.card[data-entity="' + String(a.entity_id).replace(/"/g, "") + '"]');
  if (!card) return; // assessment for a card that is not on screen: ignore
  var old = card.querySelector(".assessment");
  if (old) card.removeChild(old);
  var box = el("div", "assessment");
  var head = el("p", "meta");
  head.appendChild(el("span", "ai-tag", "Apertus"));
  head.appendChild(document.createTextNode(" " + t("as.head", "AI-generated assessment (Apertus), not source text")));
  box.appendChild(head);
  var cat = el("p", "reason");
  cat.appendChild(el("span", "badge cat-" + a.category, CATEGORY_LABELS[a.category] ? t("cat." + a.category, CATEGORY_LABELS[a.category]) : a.category));
  cat.appendChild(document.createTextNode(" " + a.explanation));
  box.appendChild(cat);
  if (a.need_coverage && a.need_coverage.length) {
    var ul = el("ul", "needlist");
    a.need_coverage.forEach(function (c) {
      // "need_query" is the server's id for the request itself, not a need the analyst wrote.
      var label = c.need_id === "need_query" ? t("as.request", "Your request") : "“" + (needText[c.need_id] || t("as.need", "Your need")) + "”";
      var li = el("li", null, label + ": " + (SUPPORT_LABELS[c.support] ? t("sup." + c.support, SUPPORT_LABELS[c.support]) : c.support));
      (c.evidence || []).forEach(function (e) {
        if (!e.version_id || !e.sentence_id) return;
        var link = el("a", null, " [" + t("as.cited", "cited sentence") + "]");
        link.href = "/api/v1/evidence/" + encodeURIComponent(e.version_id) + "/" + encodeURIComponent(e.sentence_id);
        link.target = "_blank"; link.rel = "noopener noreferrer";
        li.appendChild(link);
      });
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }
  if (a.unresolved_questions && a.unresolved_questions.length) {
    box.appendChild(el("p", "meta", t("as.open", "Open questions:") + " " + a.unresolved_questions.join(" | ")));
  }
  // Right under the badges, so the AI's verdict is the first thing read on the card.
  var tags = card.querySelector(".tags");
  if (tags && tags.nextSibling) card.insertBefore(box, tags.nextSibling); else card.appendChild(box);
  assessShown[a.entity_id] = a;
  card.classList.remove("flash");
  void card.offsetWidth; // restart the highlight animation
  card.classList.add("flash");
}

// Apertus first: with Apertus on, the analyst sees its ranking directly instead of watching
// the direct results get reshuffled. The direct results are kept as the fallback.
var resultsShown = true;   // false while we wait for Apertus' ranking
var pendingAssess = [];    // assessments that arrive before the cards are on screen
var baseRanks = {};        // entity_id -> rank in the direct results, for "Moved up by Apertus"
var showDirect = null;     // shows the direct results (fallback); null once anything is shown
var fallbackTimer = null;
var searchStarted = 0;
var currentResponse = null; // the direct search response of the current request

// Outcome box and limitations appear together with the results, never before them,
// so a new search never shows the previous one's verdict.
function renderNotes(b, byApertus) {
  lastNotes = [b, byApertus];
  renderOutcome(b, byApertus);
  var lim = document.getElementById("limitations");
  clearNode(lim);
  b.limitations.forEach(function (l) { lim.appendChild(el("li", null, serverText(l))); });
  document.getElementById("limits-box").hidden = !b.limitations.length;
}

function flushAssessments() {
  var list = pendingAssess; pendingAssess = [];
  list.forEach(renderAssessment);
}

function waitForApertus() {
  showSkeletons();
  setStatus(t("st.waiting", "Apertus is reading your request and searching other wordings. This usually takes 10 to 20 seconds."), "loading");
  var s = document.getElementById("status");
  var skip = button(t("st.skip", "Show direct results now"), function () { if (showDirect) showDirect(t("st.skipped", "Direct results, without Apertus' ranking. They update if Apertus finishes.")); });
  skip.classList.add("skip-wait");
  s.appendChild(document.createTextNode(" "));
  s.appendChild(skip);
}

function showApertusResults(results) {
  shownResults = results; shownMode = "apertus";
  resultsShown = true; showDirect = null; clearTimeout(fallbackTimer);
  var out = clearResults();
  results.forEach(function (r, i) {
    var card = renderCard(r, i);
    var was = baseRanks[r.entity_id];
    var note = !was ? t("ap.found", "Found by Apertus") : was > r.rank ? t("ap.up", "Moved up by Apertus (was #{n})", { n: was }) : "";
    if (note) { card.classList.add("moved"); card.querySelector(".tags").appendChild(el("span", "badge moved-badge", note)); }
    out.appendChild(card);
  });
  flushAssessments();
}

// After the last assessment: if every card Apertus checked is "insufficient evidence", say so above the cards.
function checkClearMatch() {
  var ids = Object.keys(assessShown);
  noClearMatch = !noNeed && ids.length > 0 && ids.every(function (id) { return assessShown[id].category === "insufficient_evidence"; });
  if (noClearMatch && lastNotes) renderOutcome.apply(null, lastNotes);
}

function startEnrichment(body, requestId, myRevision) {
  closeEvents();
  needNote("Interpreting your request…");
  function fallback(note) { if (myRevision === revision && showDirect) showDirect(note); }
  fetch("/api/v1/search/" + encodeURIComponent(requestId) + "/enrichment", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  }).then(function (r) { return r.ok ? r.json() : null; }).then(function (start) {
    if (myRevision !== revision) return;
    if (!start) { needNote(t("st.aiDown", "AI interpretation is unavailable. The direct results below are unaffected.")); fallback(""); return; }
    var es = new EventSource(start.events_url);
    eventSource = es;
    function parse(e) {
      var d = JSON.parse(e.data);
      return d.revision === revision && myRevision === revision ? d : null; // discard stale events
    }
    es.addEventListener("interpretation", function (e) {
      var d = parse(e);
      if (!d) return;
      var q = document.getElementById("query").value.trim();
      // Keep edits the analyst already made; the first interpretation seeds the lists.
      if (!userNeeds.length) {
        userNeeds = d.payload.needs.filter(function (n) { return n.origin === "user"; });
        if (!userNeeds.length && q) userNeeds = [{ schema_version: "1", need_id: "u0", text: q, origin: "user", kind: "problem" }];
      }
      suggestedNeeds = d.payload.needs.filter(function (n) { return n.origin === "suggested"; });
      d.payload.needs.forEach(function (n) { needText[n.need_id] = n.text; });
      noNeed = !d.payload.needs.length;
      renderNeeds(d.payload);
      // No other wordings means no Apertus ranking will come: show the direct results now, not after ~30 s.
      if (!(d.payload.expanded_queries || []).length)
        fallback(t("st.noWordings", "Apertus found no other wordings for this request. These are the direct results."));
    });
    es.addEventListener("reranked", function (e) {
      // T30: validated ranking over the original query plus Apertus expansions replaces the cards.
      var d = parse(e);
      if (!d || !d.payload.results.length) return;
      if (resultsShown) rerankCards(d.payload.results); // direct results already on screen (fallback)
      else { showApertusResults(d.payload.results); if (currentResponse) renderNotes(currentResponse, true); }
      renderSummary({ results: d.payload.results }, lastQuery, performance.now() - searchStarted, true);
      setStatus(t("st.ranked", "Ranked by Apertus, also using the other wordings it found."), "by-apertus");
    });
    es.addEventListener("progress", function (e) {
      var d = parse(e);
      if (d && d.payload.stage === "reranked" && d.payload.state === "skipped")
        fallback(t("st.kept", "Apertus kept the direct ranking: the request is too broad or the matches are weak."));
    });
    es.addEventListener("assessment", function (e) {
      var d = parse(e);
      if (d) renderAssessment(d.payload);
    });
    es.addEventListener("complete", function () { fallback(""); checkClearMatch(); closeEvents(); });
    es.addEventListener("error", function (e) {
      if (e.data) {
        var d = parse(e);
        if (d && d.payload.stage === "reranked") { fallback(t("st.rerankFail", "Apertus could not re-rank this time. These are the direct results.")); return; } // the stream goes on with assessments
        if (d && d.payload.stage === "assessment") {
          // Only the card assessments failed: keep Apertus' reading of the request and its ranking on screen.
          assessFailed = true;
          if (lastNeedsPayload) renderNeeds(lastNeedsPayload); else needNote(t("ai.assessFail", "Apertus could not finish its card assessments this time."));
          fallback(""); checkClearMatch(); closeEvents(); return;
        }
        if (d && d.payload.code !== "STALE_REVISION") needNote(t("st.aiDown", "AI interpretation is unavailable. The direct results below are unaffected."));
      }
      fallback("");
      closeEvents(); // no replay: the analyst can search again
    });
  }).catch(function () {
    if (myRevision === revision) { needNote(t("st.aiDown", "AI interpretation is unavailable. The direct results below are unaffected.")); fallback(""); }
  });
}

function runSearch(needs) {
  var query = document.getElementById("query").value.trim();
  if (!query) { setStatus(t("st.empty", "Enter a keyword or a short description."), "warn"); return; }
  var type = selectedType;
  var interpret = document.getElementById("interpret").checked;
  revision += 1;
  var myRevision = revision;
  closeEvents();
  clearTimeout(fallbackTimer);
  resultsShown = true; showDirect = null; pendingAssess = [];
  shownResults = null; assessShown = {}; noNeed = false; assessFailed = false; noClearMatch = false; lastSummary = null; lastNotes = null; lastNeedsPayload = null; lastNeedNote = null;
  var started = performance.now();
  searchStarted = started;
  document.body.classList.add("searched");
  queryTerms = termsOf(query);
  lastQuery = query;
  document.getElementById("summary").hidden = true;
  document.getElementById("outcome").hidden = true;
  setStatus(t("st.searching", "Searching…"), "loading");
  showSkeletons();
  clearNode(document.getElementById("limitations")); // never show the previous search's notes next to a new error
  document.getElementById("limits-box").hidden = true;
  var body = { schema_version: "1", query: query, revision: myRevision,
               entity_type: type || null, company_context: null, needs: needs || [],
               enrichment_requested: interpret };
  fetch("/api/v1/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }).then(function (r) {
    return r.json().then(function (body) { return { ok: r.ok, status: r.status, body: body }; });
  }).then(function (res) {
    if (myRevision !== revision) return; // a newer search superseded this one
    if (!res.ok) {
      clearResults();
      var e = res.body && res.body.error;
      setStatus((e ? e.message : t("st.failed", "Search failed.")) + (e && e.retryable ? " " + t("st.retry", "You can retry.") : ""), "error");
      return;
    }
    var b = res.body;
    lastRequestId = b.request_id; lastRevision = b.revision;
    var directMs = performance.now() - started;
    currentResponse = b;
    showDirect = function (note) {
      if (myRevision !== revision || resultsShown) return;
      resultsShown = true; showDirect = null; clearTimeout(fallbackTimer);
      setStatus(note || (b.results.length ? "" : t("st.none", "No results found in the indexed corpus.")), "");
      shownResults = b.results; shownMode = "direct";
      renderCards(b.results);
      renderSummary(b, query, directMs);
      renderNotes(b, false);
      flushAssessments();
    };
    if (b.enrichment_state === "pending" && b.results.length) {
      resultsShown = false;
      baseRanks = {};
      b.results.forEach(function (r) { baseRanks[r.entity_id] = r.rank; });
      waitForApertus();
      fallbackTimer = setTimeout(function () {
        if (showDirect) showDirect(t("st.slow", "Apertus is taking longer than usual. These are the direct results; they update if Apertus finishes."));
      }, 30000);
      startEnrichment(body, b.request_id, myRevision);
    } else {
      showDirect();
      if (b.enrichment_state === "pending") startEnrichment(body, b.request_id, myRevision);
      else if (b.enrichment_state === "unavailable") needNote(t("st.aiOff", "AI interpretation is not available right now. The results below are unaffected."));
      else document.getElementById("needs").hidden = true;
    }
  }).catch(function () {
    if (myRevision === revision) setStatus(t("st.offline", "Could not reach the server."), "error");
  });
}

initHero();
document.getElementById("form").addEventListener("submit", function (ev) {
  ev.preventDefault();
  userNeeds = []; suggestedNeeds = []; refineOpen = false;   // a fresh question starts fresh needs
  runSearch([]);
});
