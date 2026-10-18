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

function renderEvidence(ev) {
  var box = el("blockquote", "evidence");
  box.appendChild(el("p", "quote", ev.text));
  var a = el("a", null, ev.url);
  // Only http(s) links are made clickable.
  if (/^https?:\/\//i.test(ev.url)) { a.href = ev.url; a.rel = "noopener noreferrer"; a.target = "_blank"; }
  var meta = el("p", "meta");
  meta.appendChild(a);
  box.appendChild(meta);
  box.appendChild(el("p", "meta",
    dateLine("Source content date", ev.content_date) + " | " +
    dateLine("Last modified", ev.last_modified) + " | " +
    dateLine("Fetched", ev.fetched_at) +
    (ev.page_number ? " | page " + ev.page_number : "")));
  return box;
}

function renderFields(fields) {
  var dl = el("dl", "fields");
  var labels = { role: "Role", affiliation: "Affiliation", part_of: "Part of", led_by: "Led by", leads: "Leads",
                 members: "Members", includes: "Includes", expertise: "Expertise", projects: "Projects",
                 infrastructure: "Infrastructure", services: "Services",
                 official_contact: "Official contact (role only, not expertise)", contact: "Official contact (role only, not expertise)" };
  Object.keys(labels).forEach(function (k) {
    var vals = (fields && fields[k]) || [];
    dl.appendChild(el("dt", null, labels[k]));
    var dd = el("dd", vals.length ? null : "empty", vals.length ? null : "not stated in sources");
    vals.forEach(function (v) { dd.appendChild(el("div", null, v.value)); });
    dl.appendChild(dd);
  });
  return dl;
}

function renderCard(r) {
  var card = el("article", "card");
  card.dataset.entity = r.entity_id;
  var head = el("h3", null, r.rank + ". " + r.display_name);
  head.appendChild(el("span", "badge", r.entity_type));
  head.appendChild(el("span", "badge fresh-" + r.freshness, r.freshness));
  card.appendChild(head);
  card.appendChild(el("p", "reason", r.reason));
  card.appendChild(renderFields(r.fields));
  r.evidence.forEach(function (ev) { card.appendChild(renderEvidence(ev)); });
  return card;
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
  box.appendChild(el("p", "meta", text));
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
  var type = document.getElementById("type").value;
  var interpret = document.getElementById("interpret").checked;
  revision += 1;
  var myRevision = revision;
  closeEvents();
  setStatus("Searching…", "loading");
  clearResults();
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
    var out = clearResults();
    if (!res.ok) {
      var e = res.body && res.body.error;
      setStatus((e ? e.message : "Search failed.") + (e && e.retryable ? " You can retry." : ""), "error");
      return;
    }
    var b = res.body;
    setStatus(b.results.length ? b.results.length + " result(s)" : "No results found in the indexed corpus.", "");
    b.results.forEach(function (r) { out.appendChild(renderCard(r)); });
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

document.getElementById("form").addEventListener("submit", function (ev) {
  ev.preventDefault();
  userNeeds = []; suggestedNeeds = [];   // a fresh question starts fresh needs
  runSearch([]);
});
