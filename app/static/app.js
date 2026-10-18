"use strict";
// All text is inserted with textContent: source text is data, never markup or instructions.
var revision = 0;

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function dateLine(label, value) {
  return label + ": " + (value ? value : "unknown");
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
var EXAMPLES = [["DE", "Messung des Blutzuckers ohne Nadel für eine Smartwatch"],
                ["EN", "glucose sensors"], ["FR", "robotique pour la rééducation"]];
var FIELD_LABELS = { role: "Role", affiliation: "Affiliation", part_of: "Part of", led_by: "Led by", leads: "Leads",
                     members: "Members", includes: "Includes", expertise: "Expertise", projects: "Projects",
                     infrastructure: "Infrastructure", services: "Services",
                     official_contact: "Official contact (role only, not expertise)",
                     contact: "Official contact (role only, not expertise)" };

// Source tag from the evidence host. Unknown hosts are shown by hostname, never guessed.
function sourceOf(url) {
  var host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch (e) { return { key: "other", label: "Other" }; }
  if (host.indexOf("artorg") >= 0) return { key: "artorg", label: "ARTORG", full: "ARTORG Center" };
  if (host.indexOf("dbmr") >= 0 || host.indexOf("dcb") >= 0 || host.indexOf("diabetes") >= 0) return { key: "dcb", label: "DCB", full: "Diabetes Center Berne" };
  if (/(^|\.)unibe\.ch$/.test(host)) return { key: "unibe", label: "UniBE", full: "University of Bern" };
  return { key: "other", label: host || "Other" };
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
  return m ? +m[3] + " " + MONTHS[+m[2] - 1] + " " + m[1] : null;
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
  if (ev.content_date) parts.push("dated " + shortDate(ev.content_date));
  if (ev.last_modified) parts.push("modified " + shortDate(ev.last_modified));
  if (ev.fetched_at) parts.push("fetched " + shortDate(ev.fetched_at));
  if (ev.page_number) parts.push("page " + ev.page_number);
  var dates = el("span", null, parts.length ? " · " + parts.join(" · ") : "");
  dates.title = dateLine("Source content date", ev.content_date) + " | " + dateLine("Last modified", ev.last_modified) + " | " + dateLine("Fetched", ev.fetched_at);
  meta.appendChild(dates);
  box.appendChild(meta);
  return box;
}

// Only fields that have supported values are shown; the rest collapse into one line.
function renderFields(fields, card, notStatedTarget) {
  var dl = el("dl", "fields"), missing = [];
  Object.keys(FIELD_LABELS).forEach(function (k) {
    var vals = (fields && fields[k]) || [];
    if (!vals.length) { if (k !== "contact") missing.push(FIELD_LABELS[k].split(" (")[0].toLowerCase()); return; }
    dl.appendChild(el("dt", null, FIELD_LABELS[k]));
    var dd = el("dd");
    vals.forEach(function (v) { dd.appendChild(el("div", null, v.value)); });
    dl.appendChild(dd);
  });
  if (dl.childNodes.length) card.appendChild(dl);
  if (missing.length) (notStatedTarget || card).appendChild(el("p", "notstated", "Not stated in sources: " + missing.join(", ")));
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
  var up = button("↑", function () { moveEntry(id, -1); }); up.classList.add("mv-up"); up.setAttribute("aria-label", "Move " + item.name + " up"); up.disabled = pos === 0;
  var down = button("↓", function () { moveEntry(id, 1); }); down.classList.add("mv-down"); down.setAttribute("aria-label", "Move " + item.name + " down"); down.disabled = pos === slOrder.length - 1;
  head.appendChild(up); head.appendChild(down);
  head.appendChild(button("Remove", function () { removeEntry(id); }));
  li.appendChild(head);
  var fields = supportedFields(r);
  if (fields.length) {
    var fs = el("div", "sl-fields");
    fs.appendChild(el("span", "meta", "Show in export: "));
    fields.forEach(function (k) {
      var lab = el("label", "inline");
      var cb = el("input"); cb.type = "checkbox"; cb.checked = !item.hidden[k];
      cb.setAttribute("aria-label", "Show " + FIELD_LABELS[k].split(" (")[0] + " of " + item.name + " in the export");
      cb.addEventListener("change", function () { if (cb.checked) delete item.hidden[k]; else item.hidden[k] = true; });
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + FIELD_LABELS[k].split(" (")[0]));
      fs.appendChild(lab);
    });
    li.appendChild(fs);
  }
  var nl = el("label", "sl-note-label", "Analyst note (your text, not a source fact)");
  var note = el("textarea", "sl-note"); note.rows = 2; note.maxLength = 1000; note.value = item.note;
  note.setAttribute("aria-label", "Analyst note for " + item.name + " (your text, not a source fact)");
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
  if (!sel.firstChild) sel.appendChild(el("li", "none", "Nothing yet. Use Select on a result card."));
  Object.keys(shortlist).forEach(function (id) {
    if (shortlist[id].state !== "exclude") return;
    var li = el("li");
    li.appendChild(el("span", null, shortlist[id].name));
    li.appendChild(button("Remove", function () { removeEntry(id); }));
    exc.appendChild(li);
  });
  if (!exc.firstChild) exc.appendChild(el("li", "none", "Nothing yet"));
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
  return { title: "Bern Match shortlist", exported_at: new Date().toISOString(), request: withRequest ? lastQuery : null,
           analyst_note: listNote.trim() || null, fetched_from: fetched[0] || null, fetched_to: fetched[fetched.length - 1] || null,
           entries: entries };
}

function buildPrintView(data) {
  var view = document.getElementById("print-view");
  clearNode(view);
  view.appendChild(el("h1", null, data.title));
  view.appendChild(el("p", "meta", "Exported " + data.exported_at.slice(0, 16).replace("T", " ") + " UTC · " +
    data.entries.length + " entr" + (data.entries.length === 1 ? "y" : "ies") +
    (data.fetched_from ? " · source pages fetched " + data.fetched_from.slice(0, 10) + (data.fetched_to.slice(0, 10) !== data.fetched_from.slice(0, 10) ? " to " + data.fetched_to.slice(0, 10) : "") : "")));
  if (data.request) view.appendChild(el("p", null, "Request: " + data.request));
  if (data.analyst_note) {
    var ln = el("section", "pv-note");
    ln.appendChild(el("h3", null, "Analyst note for this list (not a source fact)"));
    ln.appendChild(el("p", null, data.analyst_note));
    view.appendChild(ln);
  }
  data.entries.forEach(function (e, i) {
    var s = el("section", "pv-entry");
    s.appendChild(el("h2", null, (i + 1) + ". " + e.name));
    s.appendChild(el("p", "meta", e.type + " · " + e.source));
    var keys = Object.keys(e.fields);
    if (keys.length) {
      var dl = el("dl", "fields");
      keys.forEach(function (k) {
        dl.appendChild(el("dt", null, FIELD_LABELS[k]));
        var dd = el("dd"); e.fields[k].forEach(function (v) { dd.appendChild(el("div", null, v)); }); dl.appendChild(dd);
      });
      s.appendChild(dl);
    }
    e.evidence.forEach(function (q) {
      var b = el("blockquote", "evidence");
      b.appendChild(el("p", "quote", q.text));
      b.appendChild(el("p", "meta", q.url));
      b.appendChild(el("p", "meta", dateLine("Source content date", q.content_date) + " | " + dateLine("Last modified", q.last_modified) + " | " + dateLine("Fetched", q.fetched_at)));
      s.appendChild(b);
    });
    if (e.analyst_note) {
      var n = el("div", "pv-note");
      n.appendChild(el("h3", null, "Analyst note (not a source fact)"));
      n.appendChild(el("p", null, e.analyst_note));
      s.appendChild(n);
    }
    view.appendChild(s);
  });
  view.appendChild(el("p", "meta pv-footer", "Facts and quotes come from the public pages named under each quote, as stored in the Bern Match index on the fetch dates shown. " +
    "Analyst notes are the analyst's own text and are not source facts. No AI-generated text is included."));
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

function langName(code) { return LANG_NAMES[code] || (code ? String(code).toUpperCase() : "unknown"); }

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
  var t = r.retrieval || {};
  var box = el("details", "why");
  box.appendChild(el("summary", null, "Why this result?"));
  var ul = el("ul", "why-list");
  function line(text) { ul.appendChild(el("li", null, text)); }
  if (t.matched_terms && t.matched_terms.length) {
    var li = el("li", null, "The source uses your words: ");
    t.matched_terms.forEach(function (w) { li.appendChild(el("span", "badge", w)); li.appendChild(document.createTextNode(" ")); });
    ul.appendChild(li);
  } else if (t.keyword_rank) {
    line("The source uses words from your request.");
  }
  if (t.dense_rank) line("The source talks about the same topic, even where the wording differs.");
  var ql = requestLang(t.query_language);
  if (ql && t.evidence_language && ql !== t.evidence_language)
    line("Found across languages: you wrote in " + langName(ql) + ", the source is in " + langName(t.evidence_language) + ".");
  if (t.query_variant === "expansion" && t.query_variants && t.query_variants.length)
    line("Found with a wording Apertus suggested: " + t.query_variants.join(", ") + ".");
  if (t.demoted_listing_page) line("Shown lower because the page looks like a list, news or report page.");
  if (!ul.firstChild) return null;
  box.appendChild(ul);
  box.appendChild(el("p", "meta", "Worked out by the search engine from the source text. Not a probability and not AI-generated."));
  return box;
}

var QUOTES_SHOWN = 2;

function renderCard(r, index) {
  var src = sourceOf(r.evidence[0].url);
  var card = el("article", "card appear src-" + src.key);
  card.style.animationDelay = Math.min(index || 0, 10) * 60 + "ms";
  card.dataset.entity = r.entity_id;
  var head = el("div", "card-head");
  var title = el("h3");
  title.appendChild(el("span", "rank", r.rank + "."));
  title.appendChild(document.createTextNode(r.display_name));
  head.appendChild(title);
  var actions = el("div", "actions");
  var sel = button("Select", function () { setShortlist(r, "select", card); }); sel.classList.add("act-select");
  var exc = button("Exclude", function () { setShortlist(r, "exclude", card); }); exc.classList.add("act-exclude");
  sel.setAttribute("aria-pressed", "false"); exc.setAttribute("aria-pressed", "false");
  actions.appendChild(sel); actions.appendChild(exc);
  head.appendChild(actions);
  card.appendChild(head);
  // Badges in plain words; anything we cannot say clearly is not shown.
  var tags = el("div", "tags");
  var srcTag = el("span", "badge tag-" + src.key, src.full || src.label);
  srcTag.title = "Where this comes from";
  tags.appendChild(srcTag);
  if (TYPE_NAMES[r.entity_type]) tags.appendChild(el("span", "badge", TYPE_NAMES[r.entity_type]));
  if (FRESHNESS[r.freshness]) {
    var fr = el("span", "badge fresh-" + r.freshness, FRESHNESS[r.freshness][0]);
    fr.title = FRESHNESS[r.freshness][1];
    tags.appendChild(fr);
  }
  var rt = r.retrieval || {};
  var ql = requestLang(rt.query_language);
  if (ql && rt.evidence_language && ql !== rt.evidence_language && LANG_NAMES[rt.evidence_language]) {
    var lt = el("span", "badge lang", "Source in " + LANG_NAMES[rt.evidence_language]);
    lt.title = "Found across languages: your request is in " + langName(ql) + ", the source page is in " + langName(rt.evidence_language) + ".";
    tags.appendChild(lt);
  }
  card.appendChild(tags);
  var why = renderWhy(r);
  if (!why) { why = el("details", "why"); why.appendChild(el("summary", null, "Why this result?")); }
  renderFields(r.fields, card, why);
  // The best quotes first; the rest fold away so one card never fills the screen.
  r.evidence.slice(0, QUOTES_SHOWN).forEach(function (ev) { card.appendChild(renderEvidence(ev)); });
  if (r.evidence.length > QUOTES_SHOWN) {
    var more = el("details", "more-quotes");
    var n = r.evidence.length - QUOTES_SHOWN;
    more.appendChild(el("summary", null, "Show " + n + " more quote" + (n === 1 ? "" : "s")));
    r.evidence.slice(QUOTES_SHOWN).forEach(function (ev) { more.appendChild(renderEvidence(ev)); });
    card.appendChild(more);
  }
  if (why.childNodes.length > 1) card.appendChild(why);
  refreshCardState(card, r.entity_id);
  return card;
}

// T30 reranked event: cards slide from their old place to the new one; new and moved cards are marked.
function rerankCards(results) {
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
    var note = !was ? "✦ Found by Apertus" : was > r.rank ? "✦ Moved up by Apertus (was #" + was + ")" : was < r.rank ? "✦ Moved down by Apertus (was #" + was + ")" : "";
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

function renderSummary(b, query, elapsedMs) {
  var box = document.getElementById("summary");
  clearNode(box);
  box.hidden = false;
  var total = b.timing_ms && typeof b.timing_ms.request_total === "number" ? b.timing_ms.request_total : elapsedMs;
  box.appendChild(el("span", "pill latency", b.results.length + " result" + (b.results.length === 1 ? "" : "s") + " in " + Math.round(total) + " ms"));
  var first = b.results[0] && b.results[0].retrieval;
  var ql = first && first.query_language && requestLang(first.query_language);
  if (ql) {
    var cross = b.results.filter(function (r) { var t = r.retrieval || {}; return t.evidence_language && t.evidence_language !== ql; }).length;
    box.appendChild(el("span", "pill", langName(ql) + " request" + (cross ? " · " + cross + " card" + (cross === 1 ? "" : "s") + " with evidence in another language" : "")));
  } else {
    var lang = guessLanguage(query);
    if (lang !== "EN") box.appendChild(el("span", "pill", "Query language detected: " + lang + " (evidence may be in another language)"));
  }
}

var OUTCOME_TEXT = {
  low_confidence: ["Low confidence", "These results are weak matches. Check the quotes before relying on them."],
  too_broad: ["Request is too broad", "Many things match. Narrow it down with one of the options below."],
  no_evidence: ["Nothing found", "The indexed corpus has no supported evidence for this request."]
};

function renderOutcome(b) {
  var box = document.getElementById("outcome");
  clearNode(box);
  var info = OUTCOME_TEXT[b.outcome];
  if (!info) { box.hidden = true; return; }
  box.hidden = false;
  box.appendChild(el("h2", null, info[0]));
  box.appendChild(el("p", null, info[1]));
  var chips = el("div", "chips");
  (b.suggestions || []).forEach(function (s) {
    chips.appendChild(button(s.label, function () { applySuggestion(s); }, "chip"));
  });
  if (chips.firstChild) box.appendChild(chips);
}

function applySuggestion(s) {
  if (s.kind === "entity_type") { setType(s.value || ""); runSearch([]); }
  else if (s.kind === "rephrase" && s.value) { document.getElementById("query").value = s.value; runSearch([]); }
}

function setType(value) {
  selectedType = value;
  var chips = document.querySelectorAll("#type-chips .chip");
  for (var i = 0; i < chips.length; i++) chips[i].setAttribute("aria-checked", String(chips[i].dataset.value === value));
}

function initHero() {
  var group = document.getElementById("type-chips");
  TYPES.forEach(function (t) {
    var c = button(t[1], function () { setType(t[0]); }, "chip");
    c.dataset.value = t[0]; c.setAttribute("role", "radio");
    group.appendChild(c);
  });
  setType("");
  var ex = document.getElementById("examples");
  EXAMPLES.forEach(function (e) {
    var b = button("", function () { document.getElementById("query").value = e[1]; userNeeds = []; suggestedNeeds = []; runSearch([]); }, "example");
    b.appendChild(el("span", "lang", e[0]));
    b.appendChild(document.createTextNode(e[1]));
    ex.appendChild(b);
  });
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
  h.appendChild(el("span", "ai-tag", "AI · Apertus"));
  h.appendChild(document.createTextNode(text));
  return h;
}

function needNote(text) {
  var box = document.getElementById("needs");
  clearNode(box);
  box.hidden = false;
  var busy = /^Interpreting/.test(text);
  box.appendChild(aiHead(busy ? "Working on your request" : "Apertus"));
  box.appendChild(el("p", "meta" + (busy ? " busy" : ""),
    busy ? "Reading your request and searching the terms researchers use: synonyms, technical terms, other languages. The results below are already usable and will update." : text));
}

var refineOpen = false; // keep "Refine" open while the analyst edits needs

function button(label, onclick, cls) {
  var b = el("button", cls || "small", label);
  b.type = "button";
  b.addEventListener("click", onclick);
  return b;
}

function renderNeeds(payload) {
  var box = document.getElementById("needs");
  clearNode(box);
  box.hidden = false;
  box.appendChild(aiHead("How Apertus read your request"));
  if (payload.synthetic || payload.decoding_mode === "synthetic") box.appendChild(el("p", "synthetic", "SYNTHETIC fixture interpretation: not a real model output."));
  // The headline: the other wordings Apertus searched, so different terms still find the experts.
  if (payload.expanded_queries && payload.expanded_queries.length) {
    box.appendChild(el("p", "meta", "Also searched as (the terms researchers use; added to the search, never to your requirements):"));
    var also = el("div", "also");
    payload.expanded_queries.forEach(function (q) {
      var chip = el("span", "wording");
      chip.appendChild(el("span", "lang", q.language));
      chip.appendChild(document.createTextNode(q.text));
      chip.title = "expands: " + q.source;
      also.appendChild(chip);
    });
    box.appendChild(also);
  }
  if (payload.clarification) {
    box.appendChild(el("p", "reason", "To focus the search: " + payload.clarification));
  }
  var refine = el("details", "refine");
  refine.open = refineOpen;
  refine.addEventListener("toggle", function () { refineOpen = refine.open; });
  refine.appendChild(el("summary", null, "Refine what the company needs (" + userNeeds.length + ")"));
  box.appendChild(refine);
  box = refine; // the editing tools live inside "Refine"
  box.appendChild(el("h3", null, "Your needs (editable)"));
  var list = el("ul", "needlist");
  userNeeds.forEach(function (n, i) {
    var li = el("li");
    var input = el("input");
    input.type = "text"; input.value = n.text; input.maxLength = 300;
    input.addEventListener("input", function () { n.text = input.value; });
    li.appendChild(input);
    li.appendChild(el("span", "badge", n.kind));
    li.appendChild(button("Remove", function () { userNeeds.splice(i, 1); renderNeeds(payload); }));
    list.appendChild(li);
  });
  box.appendChild(list);
  if (suggestedNeeds.length) {
    box.appendChild(el("h3", null, "Suggested by the model (not used until you accept)"));
    var sl = el("ul", "needlist suggested");
    suggestedNeeds.forEach(function (n, i) {
      var li = el("li");
      li.appendChild(el("span", null, n.text));
      li.appendChild(el("span", "badge", n.kind));
      li.appendChild(button("Accept", function () {
        suggestedNeeds.splice(i, 1);
        needCounter += 1;
        userNeeds.push({ schema_version: "1", need_id: "u" + needCounter, text: n.text, origin: "user", kind: n.kind });
        renderNeeds(payload);
      }));
      li.appendChild(button("Dismiss", function () { suggestedNeeds.splice(i, 1); renderNeeds(payload); }));
      sl.appendChild(li);
    });
    box.appendChild(sl);
  }
  var add = el("input"); add.type = "text"; add.placeholder = "Add a need"; add.maxLength = 300; add.id = "newneed";
  box.appendChild(add);
  box.appendChild(button("Add", function () { addNeed(add.value, payload); }));
  box.appendChild(button("Re-run search with these needs", function () { runSearch(userNeeds); }, ""));
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
  var card = document.querySelector('.card[data-entity="' + String(a.entity_id).replace(/"/g, "") + '"]');
  if (!card) return; // assessment for a card that is not on screen: ignore
  var old = card.querySelector(".assessment");
  if (old) card.removeChild(old);
  var box = el("div", "assessment");
  var head = el("p", "meta");
  head.appendChild(el("span", "ai-tag", "✦ Apertus"));
  head.appendChild(document.createTextNode(" AI-generated assessment (Apertus), not source text"));
  box.appendChild(head);
  var cat = el("p", "reason");
  cat.appendChild(el("span", "badge cat-" + a.category, CATEGORY_LABELS[a.category] || a.category));
  cat.appendChild(document.createTextNode(" " + a.explanation));
  box.appendChild(cat);
  if (a.need_coverage && a.need_coverage.length) {
    var ul = el("ul", "needlist");
    a.need_coverage.forEach(function (c) {
      var li = el("li", null, "“" + (needText[c.need_id] || c.need_id) + "”: " + (SUPPORT_LABELS[c.support] || c.support));
      (c.evidence || []).forEach(function (e) {
        if (!e.version_id || !e.sentence_id) return;
        var link = el("a", null, " [cited sentence]");
        link.href = "/api/v1/evidence/" + encodeURIComponent(e.version_id) + "/" + encodeURIComponent(e.sentence_id);
        link.target = "_blank"; link.rel = "noopener noreferrer";
        li.appendChild(link);
      });
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }
  if (a.unresolved_questions && a.unresolved_questions.length) {
    box.appendChild(el("p", "meta", "Open questions: " + a.unresolved_questions.join(" | ")));
  }
  // Right under the badges, so the AI's verdict is the first thing read on the card.
  var tags = card.querySelector(".tags");
  if (tags && tags.nextSibling) card.insertBefore(box, tags.nextSibling); else card.appendChild(box);
  card.classList.remove("flash");
  void card.offsetWidth; // restart the highlight animation
  card.classList.add("flash");
}

function startEnrichment(body, requestId, myRevision) {
  closeEvents();
  needNote("Interpreting your request… (results above are already usable)");
  fetch("/api/v1/search/" + encodeURIComponent(requestId) + "/enrichment", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  }).then(function (r) { return r.ok ? r.json() : null; }).then(function (start) {
    if (myRevision !== revision) return;
    if (!start) { needNote("AI interpretation is unavailable. The results above are unaffected."); return; }
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
      renderNeeds(d.payload);
    });
    es.addEventListener("reranked", function (e) {
      // T30: validated ranking over the original query plus Apertus expansions replaces the cards.
      var d = parse(e);
      if (!d || !d.payload.results.length) return;
      rerankCards(d.payload.results);
      setStatus("✦ Re-ranked with Apertus: " + d.payload.results.length + " results, now also searched as " +
                d.payload.expanded_queries.length + " extra wording" + (d.payload.expanded_queries.length === 1 ? "" : "s") + " (listed above)", "");
    });
    es.addEventListener("assessment", function (e) {
      var d = parse(e);
      if (d) renderAssessment(d.payload);
    });
    es.addEventListener("complete", function () { closeEvents(); });
    es.addEventListener("error", function (e) {
      if (e.data) {
        var d = parse(e);
        if (d && d.payload.code !== "STALE_REVISION") needNote("AI interpretation is unavailable. The results above are unaffected.");
      }
      closeEvents(); // no replay: the analyst can search again
    });
  }).catch(function () {
    if (myRevision === revision) needNote("AI interpretation is unavailable. The results above are unaffected.");
  });
}

function runSearch(needs) {
  var query = document.getElementById("query").value.trim();
  if (!query) { setStatus("Enter a keyword or a short description.", "warn"); return; }
  var type = selectedType;
  var interpret = document.getElementById("interpret").checked;
  revision += 1;
  var myRevision = revision;
  closeEvents();
  var started = performance.now();
  document.body.classList.add("searched");
  queryTerms = termsOf(query);
  lastQuery = query;
  document.getElementById("summary").hidden = true;
  document.getElementById("outcome").hidden = true;
  setStatus("Searching…", "loading");
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
      setStatus((e ? e.message : "Search failed.") + (e && e.retryable ? " You can retry." : ""), "error");
      return;
    }
    var b = res.body;
    lastRequestId = b.request_id; lastRevision = b.revision;
    setStatus(b.results.length ? "" : "No results found in the indexed corpus.", "");
    renderCards(b.results);
    renderSummary(b, query, performance.now() - started);
    renderOutcome(b);
    var lim = document.getElementById("limitations");
    clearNode(lim);
    b.limitations.forEach(function (l) { lim.appendChild(el("li", null, l)); });
    document.getElementById("limits-box").hidden = !b.limitations.length;
    if (b.enrichment_state === "pending") startEnrichment(body, b.request_id, myRevision);
    else if (b.enrichment_state === "unavailable") needNote("AI interpretation is not available right now. The results above are unaffected.");
    else document.getElementById("needs").hidden = true;
  }).catch(function () {
    if (myRevision === revision) setStatus("Could not reach the server.", "error");
  });
}

initHero();
document.getElementById("form").addEventListener("submit", function (ev) {
  ev.preventDefault();
  userNeeds = []; suggestedNeeds = []; refineOpen = false;   // a fresh question starts fresh needs
  runSearch([]);
});
