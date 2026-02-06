(function () {
  function $(id) {
    return document.getElementById(id);
  }

  const STEPS = [
    "Prepare",
    "Slice",
    "Generate",
    "Assemble",
    "Post",
    "Deliverables",
  ];

  const stepState = {};
  const eventIndex = new Set();
  let pollTimer = null;
  let pollStart = 0;
  let pollCount = 0;
  let lastResult = null;

  function getTaskJson() {
    return window.__TASK_JSON__ || {};
  }

  function setSummary() {
    const task = getTaskJson();
    const meta = task.meta || {};
    const avatarImg = $("avatar-preview");
    const refVideo = $("ref-preview");
    const summary = $("param-summary");
    if (summary) {
      summary.textContent = JSON.stringify(
        {
          task_id: task.task_id,
          status: task.status,
          content_lang: task.content_lang,
          pipeline_config: task.pipeline_config || {},
        },
        null,
        2
      );
    }
    const apollo = task.apollo_avatar || {};
    const advPrompt = $("adv-prompt");
    const advSeed = $("adv-seed");
    const advStrategy = $("adv-strategy");
    if (advPrompt && apollo.prompt) advPrompt.value = apollo.prompt;
    if (advSeed && apollo.seed !== undefined && apollo.seed !== null) advSeed.value = apollo.seed;
    if (advStrategy && apollo.strategy) advStrategy.value = apollo.strategy;
    if (avatarImg) {
      avatarImg.src = apollo.avatar_image_url || "";
    }
    if (refVideo && apollo.reference_video_url) {
      refVideo.innerHTML = `<source src="${apollo.reference_video_url}" type="video/mp4">`;
      refVideo.load();
    }
  }

  function stageFromEvent(evt) {
    const text = `${evt.code || ""} ${evt.message || ""}`.toLowerCase();
    if (/(prepare|hydrate|ffprobe|input)/.test(text)) return "Prepare";
    if (/(slice|split|decompose|segment)/.test(text)) return "Slice";
    if (/(generate|call_service|model)/.test(text)) return "Generate";
    if (/(assemble|stitch|concat|xfade)/.test(text)) return "Assemble";
    if (/(sub2|dub3|pack|post)/.test(text)) return "Post";
    if (/(deliver|publish|upload|manifest)/.test(text)) return "Deliverables";
    return null;
  }

  function statusFromEvent(evt) {
    const code = `${evt.code || ""}`.toLowerCase();
    if (code.includes("start")) return "running";
    if (code.includes("done") || code.includes("ready") || code.includes("success")) return "done";
    if (code.includes("skip") || code.includes("skipped")) return "done";
    if (code.includes("error") || code.includes("fail")) return "error";
    return null;
  }

  function updateStepper(events) {
    STEPS.forEach((s) => {
      if (!stepState[s]) stepState[s] = "pending";
    });
    const task = getTaskJson();
    const subStatus = String(task.subtitles_status || "").toLowerCase();
    const dubStatus = String(task.dub_status || "").toLowerCase();
    const packStatus = String(task.pack_status || "").toLowerCase();
    const scenesStatus = String(task.scenes_status || "").toLowerCase();
    if (["ready", "done"].includes(subStatus) || ["ready", "done"].includes(dubStatus) || ["ready", "done"].includes(packStatus)) {
      stepState["Post"] = "done";
    }
    if (["error", "failed"].includes(subStatus) || ["error", "failed"].includes(dubStatus) || ["error", "failed"].includes(packStatus)) {
      stepState["Post"] = "error";
    }
    if (packStatus === "ready" || packStatus === "done") {
      stepState["Deliverables"] = "done";
    } else if (scenesStatus === "skipped") {
      stepState["Deliverables"] = "skipped";
    }
    if (scenesStatus === "failed") {
      stepState["Deliverables"] = stepState["Deliverables"] === "done" ? "done" : "warning";
    }
    events.forEach((evt) => {
      const stage = stageFromEvent(evt);
      if (!stage) return;
      const status = statusFromEvent(evt);
      if (!status) return;
      stepState[stage] = status;
    });
    renderStepper();
  }

  function renderStepper() {
    const list = $("stepper-list");
    if (!list) return;
    list.innerHTML = "";
    STEPS.forEach((s) => {
      const state = stepState[s] || "pending";
      const el = document.createElement("div");
      el.className = "card";
      el.style.padding = "10px";
      el.style.minWidth = "140px";
      const label = state === "skipped" ? "SKIPPED" : state === "warning" ? "WARNING" : state.toUpperCase();
      el.innerHTML = `<div style="font-weight:700;">${s}</div><div class="muted">${label}</div>`;
      list.appendChild(el);
    });
  }

  function setOutputs(task, result) {
    const links = $("outputs-links");
    if (!links) return;
    const taskId = task.task_id || window.__TASK_ID__;
    const packReady = ["ready", "done"].includes(String(task.pack_status || "").toLowerCase());
    const scenesReady = ["ready", "done"].includes(String(task.scenes_status || "").toLowerCase());
    const scenesSkipped = String(task.scenes_status || "").toLowerCase() === "skipped";
    const scenesFailed = String(task.scenes_status || "").toLowerCase() === "failed";
    const items = [
      { label: "raw.mp4", href: `/v1/tasks/${taskId}/raw`, ready: true },
      { label: "scenes.zip", href: `/v1/tasks/${taskId}/scenes`, ready: scenesReady },
      { label: "pack.zip", href: `/v1/tasks/${taskId}/pack`, ready: packReady },
      { label: "publish bundle", href: `/v1/tasks/${taskId}/publish_bundle`, ready: packReady },
      { label: "publish hub", href: `/tasks/${taskId}/publish`, ready: true },
    ];
    if (result && result.final_video_url) {
      items.unshift({ label: "final_video_url", href: result.final_video_url, ready: true });
    }
    links.innerHTML = items
      .map((i) => {
        if (i.label === "scenes.zip" && scenesSkipped) {
          return `<span class="muted" title="Not applicable">scenes skipped</span>`;
        }
        if (i.label === "scenes.zip" && scenesFailed) {
          return `<span class="muted" title="Failed">scenes failed</span>`;
        }
        if (!i.ready) {
          if (i.label === "publish bundle") {
            return `<span class="muted" title="Not ready">see publish page</span>`;
          }
          return `<span class="muted" title="Not ready">${i.label}</span>`;
        }
        return `<a href="${i.href}" target="_blank" rel="noopener">${i.label}</a>`;
      })
      .join(" ");
  }

  function setPreviewLink(result) {
    const el = $("preview-link");
    if (!el) return;
    if (result && result.final_video_url) {
      el.innerHTML = `<a href="${result.final_video_url}" target="_blank" rel="noopener">Open Video</a>`;
      return;
    }
    el.textContent = "-";
  }

  async function fetchEvents(appendOnly) {
    const out = $("apollo-events");
    if (!out) return [];
    const url = window.__EVENTS_URL__;
    if (!url) {
      out.textContent = "-";
      return [];
    }
    const resp = await fetch(url);
    if (!resp.ok) {
      out.textContent = `Failed to load events: HTTP ${resp.status}`;
      return [];
    }
    const payload = await resp.json();
    const events = Array.isArray(payload.events) ? payload.events : [];
    const filtered = events.filter((e) => e && e.channel === "apollo_avatar");
    const fresh = [];
    filtered.forEach((e) => {
      const key = `${e.ts || ""}|${e.code || ""}|${e.message || ""}`;
      if (!eventIndex.has(key)) {
        eventIndex.add(key);
        fresh.push(e);
      }
    });
    if (!appendOnly) {
      out.textContent = filtered
        .slice()
        .reverse()
        .map((e) => `[${e.ts || ""}] [${e.code || ""}] ${e.message || ""}`)
        .join("\n");
    } else if (fresh.length) {
      out.textContent += "\n" + fresh
        .map((e) => `[${e.ts || ""}] [${e.code || ""}] ${e.message || ""}`)
        .join("\n");
    }
    updateStepper(filtered);
    const lastGenerate = filtered
      .slice()
      .reverse()
      .find((e) => e.code === "generate.done" && e.extra && e.extra.final_video_url);
    if (lastGenerate && !lastResult) {
      lastResult = { final_video_url: lastGenerate.extra.final_video_url };
      setPreviewLink(lastResult);
    }
    return filtered;
  }

  async function runGenerate() {
    const resultEl = $("apollo-result");
    if (!window.__APOLLO_GENERATE_URL__) return;
    const task = getTaskJson();
    const meta = task.meta || {};
    const apollo = task.apollo_avatar || {};
    const liveFlag = Boolean(apollo.live_enabled ?? meta.live);
    const payload = {
      live: liveFlag,
      prompt: $("adv-prompt")?.value?.trim() || apollo.prompt || "",
      seed: (() => {
        const raw = $("adv-seed")?.value?.trim();
        const val = raw ? Number(raw) : null;
        return Number.isFinite(val) ? val : null;
      })(),
      strategy: $("adv-strategy")?.value?.trim() || apollo.strategy || "default",
      force: Boolean($("adv-force")?.checked),
    };
    const resp = await fetch(window.__APOLLO_GENERATE_URL__, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      const data = await resp.json();
      lastResult = data;
      if (resultEl) {
        resultEl.textContent = JSON.stringify(data, null, 2);
      }
      setPreviewLink(data);
      setOutputs(getTaskJson(), data);
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

  function startPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer);
    }
    pollStart = Date.now();
    pollCount = 0;
    const tick = async () => {
      await fetchEvents(true);
      const elapsed = Date.now() - pollStart;
      pollCount += 1;
      if (pollCount > 60) {
        return;
      }
      const interval = elapsed < 60000 ? 1200 : elapsed < 120000 ? 2000 : 3000;
      pollTimer = setTimeout(tick, interval);
    };
    pollTimer = setTimeout(tick, 1000);
  }

  function bind() {
    $("btn-apollo-generate")?.addEventListener("click", runGenerate);
    $("btn-refresh-events")?.addEventListener("click", () => fetchEvents(false));
    setSummary();
    setOutputs(getTaskJson(), null);
    setPreviewLink(null);
    updateStepper([]);
    fetchEvents(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
