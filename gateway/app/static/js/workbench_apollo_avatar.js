(function () {
  function $(id) {
    return document.getElementById(id);
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch (_) {}
    if (!res.ok) {
      throw new Error(data?.detail || text || `HTTP ${res.status}`);
    }
    return data || {};
  }

  async function fetchEvents() {
    const out = $("apollo-events");
    if (!out) return;
    const url = window.__EVENTS_URL__;
    if (!url) {
      out.textContent = "-";
      return;
    }
    const resp = await fetch(url);
    if (!resp.ok) {
      out.textContent = `Failed to load events: HTTP ${resp.status}`;
      return;
    }
    const payload = await resp.json();
    const events = Array.isArray(payload.events) ? payload.events : [];
    const filtered = events.filter((e) => e && e.channel === "apollo_avatar").reverse();
    if (!filtered.length) {
      out.textContent = "No events.";
      return;
    }
    out.textContent = filtered
      .map((e) => `[${e.ts || ""}] [${e.code || ""}] ${e.message || ""}`)
      .join("\n");
  }

  async function runGenerate() {
    const resultEl = $("apollo-result");
    if (!window.__APOLLO_GENERATE_URL__) return;
    try {
      const data = await postJson(window.__APOLLO_GENERATE_URL__, {});
      if (resultEl) {
        resultEl.textContent = JSON.stringify(data, null, 2);
      }
      await fetchEvents();
      startPolling();
    } catch (err) {
      if (resultEl) {
        resultEl.textContent = err.message || String(err);
      }
    }
  }

  let pollTimer = null;
  let pollStart = 0;

  function startPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer);
    }
    pollStart = Date.now();
    const tick = async () => {
      await fetchEvents();
      const elapsed = Date.now() - pollStart;
      const interval = elapsed < 60000 ? 2000 : 5000;
      pollTimer = setTimeout(tick, interval);
    };
    pollTimer = setTimeout(tick, 1000);
  }

  function bind() {
    $("btn-apollo-generate")?.addEventListener("click", runGenerate);
    $("btn-refresh-events")?.addEventListener("click", fetchEvents);
    fetchEvents();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
