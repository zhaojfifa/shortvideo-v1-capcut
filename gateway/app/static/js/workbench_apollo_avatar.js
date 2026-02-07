(function () {
  function $(id) { return document.getElementById(id); }

  const STEPS = ["Prepare", "Generate", "Slice", "Assemble", "Post", "Deliverables"];

  const stepState = {};
  const eventIndex = new Set();

  let pollTimer = null;
  let pollStart = 0;
  let pollCount = 0;
  let lastResult = null;
  let pollInFlight = false;
  let pollStopped = false;
  let pollAbort = null;
  let eventsInFlight = false;

  // Publish hub fetch control
  let __PUBLISH_HUB_CACHE = null;
  let __PUBLISH_HUB_LAST_TRY_MS = 0;

  function __buildPublishHubPageUrl(taskId) { return taskId ? `/tasks/${taskId}/publish` : null; }
  function __buildPublishBundleUrl(taskId) { return taskId ? `/v1/tasks/${taskId}/publish_bundle` : null; }

  function mergeState(prev, next) {
    if (!prev) return next;
    if (prev === "error") return "error";
    if (next === "error") return "error";
    if (prev === "done") return "done";
    if (prev === "running" && next === "pending") return "running";
    if (prev === "running" && next === "done") return "done";
    return next || prev;
  }

  function isTerminalByTask(task) {
    const pack = String(task.pack_status || "").toLowerCase();
    const pub = String(task.publish_status || "").toLowerCase();
    const sub = String(task.subtitles_status || "").toLowerCase();
    const dub = String(task.dub_status || "").toLowerCase();
    const status = String(task.status || "").toLowerCase();

    const anyFailed = [pack, pub, sub, dub, status].some((s) => ["failed", "error"].includes(s));
    const allDone =
      (pack && ["done", "ready"].includes(pack)) &&
      (pub ? ["done", "ready"].includes(pub) : true);

    return anyFailed || allDone || ["done", "failed", "error"].includes(status);
  }

  function isTerminalByEvents(allEvents) {
    return (allEvents || []).some((e) => {
      const code = String(e.code || "").toLowerCase();
      return code === "post.done" || code.includes("post.error") || code.includes("post.fail");
    });
  }

  function getTaskJson() { return window.__TASK_JSON__ || {}; }

  function eventTs(e) {
    const t = e?.ts;
    if (!t) return 0;
    const n = Number(t);
    if (Number.isFinite(n)) return n;
    const d = Date.parse(String(t));
    return Number.isFinite(d) ? d : 0;
  }

  function setSummary() {
    const task = getTaskJson();
    const meta = task.meta || {};
    const avatarImg = $("avatar-preview");
    const refVideo = $("ref-preview");
    const summary = $("param-summary");

    if (summary) {
      summary.textContent = JSON.stringify({
        task_id: task.task_id,
        status: task.status,
        content_lang: task.content_lang,
        pipeline_config: task.pipeline_config || {},
        meta: meta || {}
      }, null, 2);
    }

    const apollo = task.apollo_avatar || {};
    const advPrompt = $("adv-prompt");
    const advSeed = $("adv-seed");
    const advStrategy = $("adv-strategy");
    if (advPrompt && apollo.prompt) advPrompt.value = apollo.prompt;
    if (advSeed && apollo.seed !== undefined && apollo.seed !== null) advSeed.value = apollo.seed;
    if (advStrategy && apollo.strategy) advStrategy.value = apollo.strategy;

    if (avatarImg) avatarImg.src = apollo.avatar_image_url || "";
    if (refVideo && apollo.reference_video_url) {
      refVideo.innerHTML = `<source src="${apollo.reference_video_url}" type="video/mp4">`;
      refVideo.load();
    }
  }

  function stageFromEvent(evt) {
    const code = String(evt.code || "").toLowerCase();

    if (
      code.startsWith("prepare.") ||
      code.startsWith("hydrate_raw.") ||
      code.includes("ffprobe") ||
      code.includes("input")
    ) return "Prepare";

    if (code.startsWith("generate.")) return "Generate";
    if (code.startsWith("slice.") || code.includes(".segment")) return "Slice";

    if (
      code.startsWith("assemble.") ||
      code.includes("stitch") ||
      code.includes("concat") ||
      code.includes("xfade")
    ) return "Assemble";

    if (
      code.startsWith("post.") ||
      code.startsWith("sub2_") ||
      code.startsWith("dub3_") ||
      code.includes(".pack.")
    ) return "Post";

    return null;
  }

  function statusFromEvent(evt) {
    const code = String(evt.code || "").toLowerCase();
    if (code.includes("error") || code.includes("fail") || code.endsWith(".failed")) return "error";
    if (code.endsWith(".start")) return "running";
    if (code.endsWith(".done") || code.endsWith(".ready")) return "done";
    if (code.includes(".skip")) return "skipped";
    return null;
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

  function updateStepper(allEvents) {
    STEPS.forEach((s) => { if (!stepState[s]) stepState[s] = "pending"; });

    const task = getTaskJson();
    const subStatus = String(task.subtitles_status || "").toLowerCase();
    const dubStatus = String(task.dub_status || "").toLowerCase();
    const packStatus = String(task.pack_status || "").toLowerCase();
    const publishStatus = String(task.publish_status || "").toLowerCase();

    const postDone =
      ["ready", "done"].includes(subStatus) ||
      ["ready", "done"].includes(dubStatus) ||
      ["ready", "done"].includes(packStatus);

    const postErr =
      ["error", "failed"].includes(subStatus) ||
      ["error", "failed"].includes(dubStatus) ||
      ["error", "failed"].includes(packStatus);

    if (postDone) stepState["Post"] = mergeState(stepState["Post"], "done");
    if (postErr) stepState["Post"] = mergeState(stepState["Post"], "error");

    if (["done", "ready"].includes(packStatus) || ["done", "ready"].includes(publishStatus)) {
      stepState["Deliverables"] = mergeState(stepState["Deliverables"], "done");
    } else if (["failed", "error"].includes(packStatus) || ["failed", "error"].includes(publishStatus)) {
      stepState["Deliverables"] = mergeState(stepState["Deliverables"], "error");
    }

    const sorted = (Array.isArray(allEvents) ? allEvents.slice() : []).sort((a, b) => eventTs(a) - eventTs(b));
    sorted.forEach((evt) => {
      const stage = stageFromEvent(evt);
      if (!stage) return;
      const st = statusFromEvent(evt);
      if (!st) return;
      stepState[stage] = mergeState(stepState[stage], st);
    });

    renderStepper();
  }

  // Publish hub: prefer /api/tasks/{id}/publish_hub; fallback to /v1/tasks/{id}/publish_hub
  async function fetchPublishHub(taskId, force) {
    if (!taskId) return null;

    const now = Date.now();
    const backoffMs = 3000;

    if (!force) {
      if (__PUBLISH_HUB_CACHE) return __PUBLISH_HUB_CACHE;
      if (now - __PUBLISH_HUB_LAST_TRY_MS < backoffMs) return null;
    }
    __PUBLISH_HUB_LAST_TRY_MS = now;

    const candidates = [];
    if (window.__PUBLISH_HUB_URL__) candidates.push(window.__PUBLISH_HUB_URL__);
    if (window.__APOLLO_PUBLISH_HUB_URL__) candidates.push(window.__APOLLO_PUBLISH_HUB_URL__);
    candidates.push(`/api/tasks/${taskId}/publish_hub`);
    candidates.push(`/v1/tasks/${taskId}/publish_hub`);

    for (const url of candidates) {
      if (!url) continue;
      try {
        const resp = await fetch(url, {
          headers: { "Accept": "application/json" },
          credentials: "same-origin",
          cache: "no-store",
        });

        if (!resp.ok) {
          // If unauthorized on one candidate, try the next one (do NOT permanently disable)
          continue;
        }
        const json = await resp.json();
        __PUBLISH_HUB_CACHE = json;
        return json;
      } catch (_) {
        // try next
      }
    }
    return null;
  }

  async function setOutputs(task, result, allEvents) {
    const links = $("outputs-links");
    if (!links) return;

    const taskId = task.task_id || window.__TASK_ID__;
    const hubPageUrl = __buildPublishHubPageUrl(taskId);
    const publishBundleUrl = __buildPublishBundleUrl(taskId);

    const scenesStatus = String(task.scenes_status || "").toLowerCase();
    const scenesSkipped = scenesStatus === "skipped";
    const scenesFailed = scenesStatus === "failed" || scenesStatus === "error";

    const packStatus = String(task.pack_status || "").toLowerCase();
    const publishStatus = String(task.publish_status || "").toLowerCase();
    const packReady = ["ready", "done"].includes(packStatus);
    const publishReady = ["ready", "done"].includes(publishStatus);

    // Only try to fetch deliverables when it is likely ready, or when forced by user action
    const shouldTryHub = packReady || publishReady;
    const hub = shouldTryHub ? await fetchPublishHub(taskId, false) : null;
    const d = hub && hub.deliverables ? hub.deliverables : null;

    const items = [];

    // raw.mp4: keep available
    if (d && d.raw_mp4 && d.raw_mp4.url) {
      items.push({ label: d.raw_mp4.label || "raw.mp4", href: d.raw_mp4.url, kind: "link" });
    } else {
      items.push({ label: "raw.mp4", href: `/v1/tasks/${taskId}/raw`, kind: "link" });
    }

    // scenes.zip
    if (scenesSkipped) {
      items.push({ label: "scenes skipped", kind: "muted" });
    } else if (scenesFailed) {
      items.push({ label: "scenes failed", kind: "muted" });
    } else if (d && d.scenes_zip && d.scenes_zip.url) {
      items.push({ label: d.scenes_zip.label || "scenes.zip", href: d.scenes_zip.url, kind: "link" });
    } else {
      items.push({ label: "scenes.zip", kind: "muted" });
    }

    // pack.zip
    if (d && d.pack_zip && d.pack_zip.url) {
      items.push({ label: d.pack_zip.label || "pack.zip", href: d.pack_zip.url, kind: "link" });
    } else if (packReady) {
      items.push({ label: "pack.zip", href: `/v1/tasks/${taskId}/pack`, kind: "link" });
    } else {
      items.push({ label: "pack.zip", kind: "muted" });
    }

    // publish_bundle
    if (publishBundleUrl && (publishReady || packReady || (d && d.publish_bundle))) {
      items.push({ label: "publish bundle", href: publishBundleUrl, kind: "link" });
    } else {
      items.push({ label: "publish bundle", kind: "muted" });
    }

    // publish hub page
    if (hubPageUrl) items.push({ label: "Publish Hub", href: hubPageUrl, kind: "link" });

    links.innerHTML = items.map((i) => {
      if (i.kind === "link") return `<a href="${i.href}" target="_blank" rel="noopener">${i.label}</a>`;
      return `<span class="muted">${i.label}</span>`;
    }).join(" ");
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
    if (!out) return { allEvents: [], showEvents: [] };

    const url = window.__EVENTS_URL__;
    if (!url) {
      out.textContent = "-";
      return { allEvents: [], showEvents: [] };
    }

    if (eventsInFlight) return { allEvents: [], showEvents: [] };
    eventsInFlight = true;

    if (pollAbort) { try { pollAbort.abort(); } catch (_) {} }
    pollAbort = new AbortController();

    let resp;
    try {
      resp = await fetch(url, { signal: pollAbort.signal, cache: "no-store", credentials: "same-origin" });
    } catch (_) {
      eventsInFlight = false;
      return { allEvents: [], showEvents: [] };
    }

    if (!resp.ok) {
      out.textContent = `Failed to load events: HTTP ${resp.status}`;
      eventsInFlight = false;
      return { allEvents: [], showEvents: [] };
    }

    const payload = await resp.json();
    const allEvents = Array.isArray(payload.events) ? payload.events : [];
    const allSorted = allEvents.slice().sort((a, b) => eventTs(a) - eventTs(b));

    // For UI display we keep apollo_avatar channel when present, but terminal logic uses allEvents.
    const show = allEvents.filter((e) => !e?.channel || e.channel === "apollo_avatar");
    const showSorted = show.slice().sort((a, b) => eventTs(a) - eventTs(b));

    const fresh = [];
    showSorted.forEach((e) => {
      const key = `${e.ts || ""}|${e.code || ""}|${e.message || ""}|${e.channel || ""}`;
      if (!eventIndex.has(key)) {
        eventIndex.add(key);
        fresh.push(e);
      }
    });

    if (!appendOnly) {
      out.textContent = showSorted
        .slice()
        .reverse()
        .map((e) => `[${e.ts || ""}] [${e.code || ""}] ${e.message || ""}`)
        .join("\n");
    } else if (fresh.length) {
      out.textContent += "\n" + fresh
        .map((e) => `[${e.ts || ""}] [${e.code || ""}] ${e.message || ""}`)
        .join("\n");
    }

    updateStepper(allSorted);

    const lastGenerate = allSorted.slice().reverse().find((e) => {
      return String(e.code || "").toLowerCase() === "generate.done" && e.extra && e.extra.final_video_url;
    });

    if (lastGenerate) {
      lastResult = { final_video_url: lastGenerate.extra.final_video_url };
      setPreviewLink(lastResult);
    }

    eventsInFlight = false;
    return { allEvents: allSorted, showEvents: showSorted };
  }

  function stopPolling() {
    pollStopped = true;
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = null;
    if (pollAbort) { try { pollAbort.abort(); } catch (_) {} }
    pollAbort = null;
  }

  function nextIntervalMs(elapsedMs) {
    if (elapsedMs < 30000) return 1200;
    if (elapsedMs < 120000) return 2500;
    if (elapsedMs < 300000) return 5000;
    return 8000;
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
      credentials: "same-origin",
    });

    if (resp.ok) {
      const data = await resp.json();
      lastResult = data;
      if (resultEl) resultEl.textContent = JSON.stringify(data, null, 2);

      stepState["Generate"] = mergeState(stepState["Generate"], "running");
      renderStepper();

      setPreviewLink(data);

      await fetchEvents(false);
      startPolling();
      return;
    }

    let detail = null;
    try { detail = await resp.json(); } catch (_) { detail = null; }
    if (resultEl) {
      resultEl.textContent = detail ? JSON.stringify(detail, null, 2) : `${resp.status} ${resp.statusText}`;
    }
  }

  function startPolling() {
    stopPolling();
    pollStopped = false;
    pollStart = Date.now();
    pollCount = 0;

    const tick = async () => {
      if (pollStopped) return;
      if (document.visibilityState === "hidden") { stopPolling(); return; }
      if (pollInFlight) { pollTimer = setTimeout(tick, 800); return; }

      pollInFlight = true;
      try {
        const { allEvents } = await fetchEvents(true);
        await setOutputs(getTaskJson(), lastResult, allEvents);

        const task = getTaskJson();
        if (isTerminalByEvents(allEvents) || isTerminalByTask(task)) {
          stopPolling();
          return;
        }
      } finally {
        pollInFlight = false;
      }

      pollCount += 1;
      const elapsed = Date.now() - pollStart;
      if (pollCount > 120) { stopPolling(); return; }
      pollTimer = setTimeout(tick, nextIntervalMs(elapsed));
    };

    pollTimer = setTimeout(tick, 800);
  }

  function bind() {
    $("btn-apollo-generate")?.addEventListener("click", runGenerate);
    $("btn-refresh-events")?.addEventListener("click", () => fetchEvents(false));

    setSummary();
    setPreviewLink(null);
    updateStepper([]);
    setOutputs(getTaskJson(), null, []);

    fetchEvents(false).then(async ({ allEvents }) => {
      await setOutputs(getTaskJson(), lastResult, allEvents);
      const task = getTaskJson();
      if (!isTerminalByEvents(allEvents) && !isTerminalByTask(task)) startPolling();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();

  window.addEventListener("beforeunload", stopPolling);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") stopPolling();
  });
})();
