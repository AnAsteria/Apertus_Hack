"use strict";
// T13 operator page. All text is inserted with textContent. The token lives in this closure only.
(function () {
  var token = "";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function status(text, kind) { var s = document.getElementById("status"); s.textContent = text; s.className = "status " + (kind || ""); }
  function day(iso) { return iso ? iso.slice(0, 16).replace("T", " ") + " UTC" : "unknown"; }

  function call(method, url, body) {
    return fetch(url, { method: method, headers: { "Content-Type": "application/json", "X-Admin-Token": token },
                        body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function pills(box, obj, empty) {
    clear(box);
    var keys = Object.keys(obj || {});
    if (!keys.length) { box.appendChild(el("span", "meta", empty)); return; }
    keys.forEach(function (k) { box.appendChild(el("span", "pill", k + ": " + obj[k])); });
  }

  function refresh(source, btn) {
    btn.disabled = true;
    call("POST", "/api/v1/admin/refresh", { schema_version: "1", source_id: source }).then(function (r) {
      if (r.ok) status("Queued refresh for " + source + " (job " + r.body.job_id + "). " + r.body.note, "");
      else status((r.body.error && r.body.error.message) || "Refresh failed.", "warn");
      load();
    }).catch(function () { status("Could not reach the server.", "error"); btn.disabled = false; });
  }

  function render(c) {
    document.getElementById("overview").hidden = false;
    var t = c.totals || {};
    var totals = document.getElementById("totals");
    clear(totals);
    if (c.totals) {
      totals.appendChild(el("span", "pill latency", t.pages + " pages"));
      totals.appendChild(el("span", "pill", t.sentences + " sentences"));
      totals.appendChild(el("span", "pill", c.sources.length + " sources"));
      if (t.retired || t.suppressed) totals.appendChild(el("span", "pill", t.retired + " retired, " + t.suppressed + " suppressed"));
    }
    document.getElementById("note").textContent = c.note || "";
    var jobs = document.getElementById("jobs");
    clear(jobs);
    var states = el("div", "summary"); pills(states, c.jobs_by_state, "No jobs recorded."); jobs.appendChild(states);
    if (c.recent_jobs && c.recent_jobs.length) {
      var ul = el("ul", "limitations");
      c.recent_jobs.forEach(function (j) { ul.appendChild(el("li", null, day(j.started_at) + " · " + j.kind + " · " + j.source_id + " · " + j.state + (j.error_codes && j.error_codes.length ? " · " + j.error_codes.join(", ") : ""))); });
      jobs.appendChild(ul);
    }
    pills(document.getElementById("feedback"), c.feedback_by_action, "No feedback yet.");
    var body = document.querySelector("#sources tbody");
    clear(body);
    c.sources.forEach(function (s) {
      var tr = el("tr");
      [s.source, s.pages, s.active, s.retired, s.suppressed, s.sentences, day(s.fetched_last)].forEach(function (v) { tr.appendChild(el("td", null, String(v))); });
      var td = el("td"), b = el("button", "small", "Queue refresh");
      b.type = "button"; b.setAttribute("aria-label", "Queue a refresh of " + s.source);
      b.addEventListener("click", function () { refresh(s.source, b); });
      td.appendChild(b); tr.appendChild(td);
      body.appendChild(tr);
    });
  }

  function load() {
    return call("GET", "/api/v1/admin/coverage").then(function (r) {
      if (!r.ok) {
        document.getElementById("overview").hidden = true;
        status(r.status === 401 ? "Wrong or missing token." : r.status === 403 ? "The admin API is not enabled on this server." : "Could not load coverage.", "error");
        return;
      }
      render(r.body);
    }).catch(function () { status("Could not reach the server.", "error"); });
  }

  document.getElementById("login").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var input = document.getElementById("token");
    token = input.value;
    input.value = "";
    status("Loading…", "loading");
    load().then(function () { if (!document.getElementById("overview").hidden) status("", ""); });
  });
})();
