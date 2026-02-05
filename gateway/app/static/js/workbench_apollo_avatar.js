(function () {
  function $(id) {
    return document.getElementById(id);
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
    const resp = await fetch(window.__APOLLO_GENERATE_URL__, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (resp.ok) {
      const data = await resp.json();
      if (resultEl) {
        if (data.final_video_url) {
          resultEl.innerHTML = `<a href="${data.final_video_url}" target="_blank" rel="noopener">final_video_url</a>`;
        } else {
          resultEl.textContent = JSON.stringify(data, null, 2);
        }
      }
      await fetchEvents();
      startPolling();
      return;
    }
    let detail = null;
    try {
      detail = await resp.json();
    } catch (_) {
      detail = null;
    }
    if (resultEl) {
      if (detail) {
        resultEl.textContent = JSON.stringify(detail, null, 2);
      } else {
        resultEl.textContent = `${resp.status} ${resp.statusText}`;
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
