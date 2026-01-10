(() => {
  const logEl = document.getElementById("log");
  const inFlight = {
    parse: false,
    subtitles: false,
    dub: false,
    pack: false,
    status: false,
  };

  const POLL_INTERVAL_MS = 3000;
  let subsPoller = null;
  let dubPoller = null;
  let subsPollInFlight = false;
  let dubPollInFlight = false;

  const buttons = {
    parse: ["btn-step1", "btn-parse"],
    subtitles: ["btn-step2", "btn-subtitles"],
    dub: ["btn-step3", "btn-dub"],
    pack: ["btn-step4", "btn-pack"],
    status: ["btn-status"],
    all: ["btn-run-all"],
    clear: ["btn-clear-log"],
    generate: ["btn-generate-task", "btn-generate-from-link", "btn-reset-task"],
  };

  function getEl(id) {
    return document.getElementById(id);
  }

  function log(message) {
    if (!logEl) return;
    const now = new Date().toISOString();
    logEl.textContent += `\n[${now}] ${message}`;
    logEl.scrollTop = logEl.scrollHeight;
  }

  function clearLog() {
    if (!logEl) return;
    logEl.textContent = "";
    log("Ready.");
  }

  function taskId() {
    const el = getEl("taskId");
    return el ? el.value.trim() : "";
  }

  function platform() {
    const el = getEl("platform");
    return el ? el.value : "";
  }

  function link() {
    const el = getEl("link");
    return el ? el.value.trim() : "";
  }

  function voiceId() {
    const el = getEl("voiceId");
    return el ? el.value.trim() || "mm_female_1" : "mm_female_1";
  }

  function setButtonsDisabled(group, disabled) {
    (buttons[group] || []).forEach((id) => {
      const el = getEl(id);
      if (el) {
        el.disabled = disabled;
      }
    });
  }

  function updateDownloadLinks(id) {
    const rawLink = getEl("rawLink");
    const originLink = getEl("originLink");
    const mmLink = getEl("mmLink");
    const mmTxtLink = getEl("mmTxtLink");
    const audioLink = getEl("audioLink");
    const packLink = getEl("packLink");
    const scenesLink = getEl("scenesLink");
    if (rawLink) rawLink.href = `/v1/tasks/${id}/raw`;
    if (originLink) originLink.href = `/v1/tasks/${id}/subs_origin`;
    if (mmLink) mmLink.href = `/v1/tasks/${id}/subs_mm`;
    if (mmTxtLink) mmTxtLink.href = `/v1/tasks/${id}/mm_txt`;
    if (audioLink) audioLink.href = `/v1/tasks/${id}/audio_mm`;
    if (packLink) packLink.href = `/v1/tasks/${id}/pack`;
    if (scenesLink) scenesLink.href = `/v1/tasks/${id}/scenes`;
  }

  function startSubtitlesPolling(id) {
    if (subsPoller) stopSubtitlesPolling();
    subsPoller = setInterval(async () => {
      if (subsPollInFlight) return;
      subsPollInFlight = true;
      try {
        const status = await fetchJson(`/v1/tasks/${id}/status`, { method: "GET" });
        if (status.subtitles_status === "ready") {
          log("Subtitles ready.");
          stopSubtitlesPolling();
          updateDownloadLinks(id);
        } else if (status.subtitles_status === "error") {
          log(`Subtitles failed: ${status.subtitles_error || "unknown"}`);
          stopSubtitlesPolling();
        }
      } catch (err) {
        log(`Subtitles status poll failed: ${err}`);
        stopSubtitlesPolling();
      } finally {
        subsPollInFlight = false;
      }
    }, POLL_INTERVAL_MS);
  }

  function stopSubtitlesPolling() {
    if (!subsPoller) return;
    clearInterval(subsPoller);
    subsPoller = null;
  }

  function startDubPolling(id) {
    if (dubPoller) stopDubPolling();
    dubPoller = setInterval(async () => {
      if (dubPollInFlight) return;
      dubPollInFlight = true;
      try {
        const status = await fetchJson(`/v1/tasks/${id}/status`, { method: "GET" });
        if (status.dub_status === "ready") {
          log("Dub audio ready.");
          stopDubPolling();
          updateDownloadLinks(id);
        } else if (status.dub_status === "error") {
          log(`Dub failed: ${status.dub_error || "unknown"}`);
          stopDubPolling();
        }
      } catch (err) {
        log(`Dub status poll failed: ${err}`);
        stopDubPolling();
      } finally {
        dubPollInFlight = false;
      }
    }, POLL_INTERVAL_MS);
  }

  function stopDubPolling() {
    if (!dubPoller) return;
    clearInterval(dubPoller);
    dubPoller = null;
  }

  async function waitForStepReady(id, stepKey) {
    const statusKey = stepKey === "dub" ? "dub_status" : "subtitles_status";
    const errorKey = stepKey === "dub" ? "dub_error" : "subtitles_error";
    while (true) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      const status = await fetchJson(`/v1/tasks/${id}/status`, { method: "GET" });
      const state = status[statusKey];
      if (state === "ready") {
        return status;
      }
      if (state === "error") {
        throw new Error(`${stepKey} failed: ${status[errorKey] || "unknown"}`);
      }
    }
  }

  async function fetchJson(url, opts) {
    const res = await fetch(url, opts);
    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    if (!res.ok) {
      const text = await res.text();
      const snippet = text.length > 300 ? `${text.slice(0, 300)}...` : text;
      throw new Error(`HTTP ${res.status}: ${snippet}`);
    }
    if (contentType.includes("application/json")) {
      return res.json();
    }
    const body = await res.text();
    throw new Error(`Expected JSON but got ${contentType || "unknown"}: ${body.slice(0, 120)}`);
  }

  async function fetchJsonWithStatus(url, opts) {
    const res = await fetch(url, opts);
    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    if (!res.ok) {
      const text = await res.text();
      const snippet = text.length > 300 ? `${text.slice(0, 300)}...` : text;
      throw new Error(`HTTP ${res.status}: ${snippet}`);
    }
    if (!contentType.includes("application/json")) {
      const body = await res.text();
      throw new Error(`Expected JSON but got ${contentType || "unknown"}: ${body.slice(0, 120)}`);
    }
    return { status: res.status, json: await res.json() };
  }

  function generateTaskId() {
    const stamp = new Date().toISOString().slice(0, 19);
    const compact = stamp.replace(/[-:]/g, "").replace("T", "");
    const el = getEl("taskId");
    if (el) {
      el.value = `task_${compact}`;
    }
    log("Task ID updated.");
  }

  function generateFromLink() {
    const rawLink = link();
    if (!rawLink) {
      log("Missing link.");
      return;
    }
    let safe = rawLink;
    if (safe.startsWith("https://")) safe = safe.slice(8);
    if (safe.startsWith("http://")) safe = safe.slice(7);
    safe = safe.split(/[/?#]/)[0];
    const el = getEl("taskId");
    if (el) {
      el.value = `task_${safe.slice(0, 16)}`;
    }
    log("Task ID generated.");
  }

  function resetTaskForm() {
    const taskIdEl = getEl("taskId");
    const platformEl = getEl("platform");
    const linkEl = getEl("link");
    const voiceEl = getEl("voiceId");
    if (taskIdEl) taskIdEl.value = "demo_v1";
    if (platformEl) platformEl.value = "douyin";
    if (linkEl) linkEl.value = "";
    if (voiceEl) voiceEl.value = "mm_female_1";
    updateDownloadLinks("demo_v1");
    log("Form reset.");
  }

  async function runParse() {
    if (inFlight.parse) return;
    inFlight.parse = true;
    setButtonsDisabled("parse", true);
    setButtonsDisabled("all", true);
    const body = { task_id: taskId(), platform: platform(), link: link() };
    log(`Calling /v1/parse for ${body.task_id}.`);
    try {
      const json = await fetchJson("/v1/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const output = getEl("parseOutput");
      if (output) output.textContent = JSON.stringify(json, null, 2);
      updateDownloadLinks(body.task_id);
      log("Parse done.");
      return json;
    } catch (err) {
      log(`Parse failed: ${err}`);
      throw err;
    } finally {
      inFlight.parse = false;
      setButtonsDisabled("parse", false);
      setButtonsDisabled("all", false);
    }
  }

  async function runSubtitles() {
    if (inFlight.subtitles) return;
    inFlight.subtitles = true;
    setButtonsDisabled("subtitles", true);
    setButtonsDisabled("all", true);
    const body = { task_id: taskId(), target_lang: "my", force: false, translate: true, with_scenes: true };
    log("Calling /v1/subtitles.");
    try {
      const { status, json } = await fetchJsonWithStatus("/v1/subtitles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (status === 202 || json.queued) {
        log("Subtitles queued; polling status...");
        startSubtitlesPolling(body.task_id);
        return json;
      }
      const output = getEl("subsOutput");
      if (output) output.textContent = JSON.stringify(json, null, 2);
      const originPreview = getEl("originPreview");
      const mmPreview = getEl("mmPreview");
      if (originPreview) originPreview.textContent = (json.origin_preview || []).join("\n") || "(empty)";
      if (mmPreview) mmPreview.textContent = (json.mm_preview || []).join("\n") || "(empty)";
      if (json.segments_json) {
        log(`Segments JSON ready: ${json.segments_json}`);
      }
      log("Subtitles generated.");
      return json;
    } catch (err) {
      log(`Subtitles failed: ${err}`);
      throw err;
    } finally {
      inFlight.subtitles = false;
      setButtonsDisabled("subtitles", false);
      setButtonsDisabled("all", false);
    }
  }

  async function runDub() {
    if (inFlight.dub) return;
    inFlight.dub = true;
    setButtonsDisabled("dub", true);
    setButtonsDisabled("all", true);
    const body = { task_id: taskId(), voice_id: voiceId(), force: false, target_lang: "my" };
    log(`Calling /v1/dub for ${body.task_id}.`);
    try {
      const { status, json } = await fetchJsonWithStatus("/v1/dub", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (status === 202 || json.queued) {
        log("Dub queued; polling status...");
        startDubPolling(body.task_id);
        return json;
      }
      const output = getEl("dubOutput");
      if (output) output.textContent = JSON.stringify(json, null, 2);
      const player = getEl("audioPlayer");
      if (player) {
        player.src = `/v1/tasks/${body.task_id}/audio_mm`;
        player.style.display = "block";
      }
      updateDownloadLinks(body.task_id);
      log("Dub audio ready.");
      return json;
    } catch (err) {
      log(`Dub failed: ${err}`);
      throw err;
    } finally {
      inFlight.dub = false;
      setButtonsDisabled("dub", false);
      setButtonsDisabled("all", false);
    }
  }

  async function runPack() {
    if (inFlight.pack) return;
    inFlight.pack = true;
    setButtonsDisabled("pack", true);
    setButtonsDisabled("all", true);
    const body = { task_id: taskId() };
    log(`Calling /v1/pack for ${body.task_id}.`);
    try {
      const json = await fetchJson("/v1/pack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const output = getEl("packOutput");
      if (output) output.textContent = JSON.stringify(json, null, 2);
      updateDownloadLinks(body.task_id);
      log("Pack ready.");
      return json;
    } catch (err) {
      log(`Pack failed: ${err}`);
      throw err;
    } finally {
      inFlight.pack = false;
      setButtonsDisabled("pack", false);
      setButtonsDisabled("all", false);
    }
  }

  async function refreshStatus() {
    if (inFlight.status) return;
    inFlight.status = true;
    setButtonsDisabled("status", true);
    const id = taskId();
    log(`Calling /v1/tasks/${id}/status.`);
    try {
      const json = await fetchJson(`/v1/tasks/${id}/status`, { method: "GET" });
      const output = getEl("statusOutput");
      if (output) output.textContent = JSON.stringify(json, null, 2);
      updateDownloadLinks(id);
      log("Status refreshed.");
      return json;
    } catch (err) {
      log(`Status failed: ${err}`);
      throw err;
    } finally {
      inFlight.status = false;
      setButtonsDisabled("status", false);
    }
  }

  async function runFullPipeline() {
    try {
      const id = taskId();
      await runParse();
      const subsResult = await runSubtitles();
      if (subsResult && subsResult.queued) {
        log("Waiting for subtitles to finish...");
        await waitForStepReady(id, "subtitles");
      }
      const dubResult = await runDub();
      if (dubResult && dubResult.queued) {
        log("Waiting for dub to finish...");
        await waitForStepReady(id, "dub");
      }
      await runPack();
    } catch (err) {
      log(`Pipeline stopped: ${err}`);
    }
  }

  window.addEventListener("error", (event) => {
    log(`Runtime error: ${event.message || event.error}`);
  });

  window.addEventListener("unhandledrejection", (event) => {
    log(`Unhandled rejection: ${event.reason}`);
  });

  document.addEventListener("DOMContentLoaded", () => {
    updateDownloadLinks(taskId());
    const map = [
      ["btn-generate-task", generateTaskId],
      ["btn-generate-from-link", generateFromLink],
      ["btn-reset-task", resetTaskForm],
      ["btn-step1", runParse],
      ["btn-step2", runSubtitles],
      ["btn-step3", runDub],
      ["btn-step4", runPack],
      ["btn-run-all", runFullPipeline],
      ["btn-parse", runParse],
      ["btn-subtitles", runSubtitles],
      ["btn-dub", runDub],
      ["btn-pack", runPack],
      ["btn-status", refreshStatus],
      ["btn-clear-log", clearLog],
    ];
    map.forEach(([id, handler]) => {
      const el = getEl(id);
      if (el) {
        el.addEventListener("click", handler);
      }
    });
  });
})();
