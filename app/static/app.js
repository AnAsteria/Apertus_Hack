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
  var labels = { affiliation: "Affiliation", expertise: "Expertise", contact: "Contact",
                 projects: "Projects", infrastructure: "Infrastructure / services" };
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

function search(ev) {
  ev.preventDefault();
  var query = document.getElementById("query").value.trim();
  if (!query) { setStatus("Enter a keyword or a short description.", "warn"); return; }
  var type = document.getElementById("type").value;
  revision += 1;
  var myRevision = revision;
  setStatus("Searching…", "loading");
  clearResults();
  fetch("/api/v1/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schema_version: "1", query: query, revision: myRevision,
                           entity_type: type || null, company_context: null, needs: [],
                           enrichment_requested: false })
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
    while (lim.firstChild) lim.removeChild(lim.firstChild);
    b.limitations.forEach(function (l) { lim.appendChild(el("li", null, l)); });
  }).catch(function () {
    if (myRevision === revision) setStatus("Could not reach the server.", "error");
  });
}

document.getElementById("form").addEventListener("submit", search);
