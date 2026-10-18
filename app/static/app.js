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

var TYPE_ICONS = { person: "👤", unit: "🏛", project: "🧪", infrastructure: "🔬", service: "🛠" };
var TYPES = [["", "Anything"], ["person", "People"], ["unit", "Groups"], ["project", "Projects"],
             ["infrastructure", "Infrastructure"], ["service", "Services"]];
var EXAMPLES = [["EN", "continuous glucose monitoring sensors"], ["DE", "Bildgebung in der Herzchirurgie"],
                ["FR", "robotique pour la rééducation"]];
var FIELD_LABELS = { role: "Role", affiliation: "Affiliation", part_of: "Part of", led_by: "Led by", leads: "Leads",
                     members: "Members", includes: "Includes", expertise: "Expertise", projects: "Projects",
                     infrastructure: "Infrastructure", services: "Services",
                     official_contact: "Official contact (role only, not expertise)",
                     contact: "Official contact (role only, not expertise)" };

// Source tag from the evidence host. Unknown hosts are shown by hostname, never guessed.
function sourceOf(url) {
  var host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch (e) { return { key: "other", label: "Other" }; }
  if (host.indexOf("artorg") >= 0) return { key: "artorg", label: "ARTORG" };
  if (host.indexOf("dbmr") >= 0 || host.indexOf("dcb") >= 0 || host.indexOf("diabetes") >= 0) return { key: "dcb", label: "DCB" };
  if (/(^|\.)unibe\.ch$/.test(host)) return { key: "unibe", label: "UniBE" };
  return { key: "other", label: host || "Other" };
}

function termsOf(q) {
  var seen = {};
  return (q.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) || []).filter(function (w) {
    if (seen[w]) return false; seen[w] = true; return true;
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

function renderEvidence(ev) {
  var box = el("blockquote", "evidence");
  box.appendChild(highlighted(el("p", "quote"), ev.text, queryTerms));
  var meta = el("p", "meta");
  var a = el("a", null, "Open source");
  // Only http(s) links are made clickable.
  if (/^https?:\/\//i.test(ev.url)) { a.href = ev.url; a.rel = "noopener noreferrer"; a.target = "_blank"; }
  a.title = ev.url;
  meta.appendChild(a);
  meta.appendChild(document.createTextNode(" · " + ev.url));
  box.appendChild(meta);
  box.appendChild(el("p", "meta",
    dateLine("Source content date", ev.content_date) + " | " +
    dateLine("Last modified", ev.last_modified) + " | " +
    dateLine("Fetched", ev.fetched_at) +
    (ev.page_number ? " | page " + ev.page_number : "")));
  return box;
}

// Only fields that have supported values are shown; the rest collapse into one line.
function renderFields(fields, card) {
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
  if (missing.length) card.appendChild(el("p", "notstated", "Not stated in sources: " + missing.join(", ")));
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

function setShortlist(r, state, card) {
  var cur = shortlist[r.entity_id];
  if (cur && cur.state === state) { delete shortlist[r.entity_id]; }
  else { shortlist[r.entity_id] = { name: r.display_name, state: state }; sendFeedback(r, state); }
  if (card) refreshCardState(card, r.entity_id);
  renderShortlist();
}

function refreshCardState(card, id) {
  var st = shortlist[id] ? shortlist[id].state : "";
  card.classList.toggle("excluded", st === "exclude");
  var sel = card.querySelector(".act-select"), exc = card.querySelector(".act-exclude");
  if (sel) sel.setAttribute("aria-pressed", String(st === "select"));
  if (exc) exc.setAttribute("aria-pressed", String(st === "exclude"));
}

function renderShortlist() {
  var ids = Object.keys(shortlist), n = 0;
  ["select", "exclude"].forEach(function (state) {
    var ul = document.getElementById(state === "select" ? "sl-selected" : "sl-excluded");
    clearNode(ul);
    ids.forEach(function (id) {
      var item = shortlist[id];
      if (item.state !== state) return;
      if (state === "select") n += 1;
      var li = el("li");
      li.appendChild(el("span", null, item.name));
      li.appendChild(button("Remove", function () {
        delete shortlist[id];
        var c = document.querySelector('.card[data-entity="' + id.replace(/"/g, "") + '"]');
        if (c) refreshCardState(c, id);
        renderShortlist();
      }));
      ul.appendChild(li);
    });
    if (!ul.firstChild) ul.appendChild(el("li", "none", "Nothing yet"));
  });
  document.getElementById("shortlist-count").textContent = String(n);
}

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
  var tags = el("div", "tags");
  tags.appendChild(el("span", "badge tag-" + src.key, src.label));
  tags.appendChild(el("span", "badge", (TYPE_ICONS[r.entity_type] || "") + " " + r.entity_type));
  tags.appendChild(el("span", "badge fresh-" + r.freshness, r.freshness));
  card.appendChild(tags);
  card.appendChild(el("p", "reason", r.reason));
  renderFields(r.fields, card);
  r.evidence.forEach(function (ev) { card.appendChild(renderEvidence(ev)); });
  refreshCardState(card, r.entity_id);
  return card;
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
  var lang = guessLanguage(query);
  if (lang !== "EN") box.appendChild(el("span", "pill", "Query language detected: " + lang + " (evidence may be in another language)"));
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
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && !drawer.hidden) { drawer.hidden = true; toggle.setAttribute("aria-expanded", "false"); toggle.focus(); }
  });
  renderShortlist();
}

var eventSource = null;
var userNeeds = [];      // needs the analyst controls (origin "user")
var suggestedNeeds = []; // model suggestions: never sent as requirements until accepted
var needCounter = 0;

function closeEvents() {
  if (eventSource) { eventSource.close(); eventSource = null; }
}

function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function needNote(text) {
  var box = document.getElementById("needs");
  clearNode(box);
  box.hidden = false;
  box.appendChild(el("p", "meta" + (/^Interpreting/.test(text) ? " busy" : ""), text.replace(/^Interpreting/, "Apertus is analysing") ));
}

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
  if (payload.synthetic || payload.decoding_mode === "synthetic") box.appendChild(el("p", "synthetic", "SYNTHETIC fixture interpretation: not a real model output."));
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
  if (payload.expanded_queries && payload.expanded_queries.length) {
    box.appendChild(el("h3", null, "Alternative wording (read-only; added to recall, never to requirements)"));
    var chips = el("p");
    payload.expanded_queries.forEach(function (q) { var chip = el("span", "badge", q.language + ": " + q.text); chip.title = "expands: " + q.source; chips.appendChild(chip); });
    box.appendChild(chips);
  }
  if (payload.clarification) {
    box.appendChild(el("p", "reason", "To focus the search: " + payload.clarification));
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
  var head = el("p", "meta", "AI-generated assessment (Apertus), not source text");
  box.appendChild(head);
  var cat = el("p", "reason");
  cat.appendChild(el("span", "badge cat-" + a.category, CATEGORY_LABELS[a.category] || a.category));
  cat.appendChild(document.createTextNode(" " + a.explanation));
  box.appendChild(cat);
  if (a.need_coverage && a.need_coverage.length) {
    var ul = el("ul", "needlist");
    a.need_coverage.forEach(function (c) {
      var li = el("li", null, c.need_id + ": " + (SUPPORT_LABELS[c.support] || c.support));
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
  card.appendChild(box);
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
      renderNeeds(d.payload);
    });
    es.addEventListener("reranked", function (e) {
      // T30: validated ranking over the original query plus Apertus expansions replaces the cards.
      var d = parse(e);
      if (!d || !d.payload.results.length) return;
      renderCards(d.payload.results);
      setStatus(d.payload.results.length + " result(s), updated with Apertus query expansion (" +
                d.payload.expanded_queries.join(", ") + ")", "");
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
  document.getElementById("summary").hidden = true;
  document.getElementById("outcome").hidden = true;
  setStatus("Searching…", "loading");
  showSkeletons();
  clearNode(document.getElementById("limitations")); // never show the previous search's notes next to a new error
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
  userNeeds = []; suggestedNeeds = [];   // a fresh question starts fresh needs
  runSearch([]);
});
