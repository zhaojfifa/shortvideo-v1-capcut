(function () {
  function t(key, vars) {
    if (window.__V185_I18N__ && typeof window.__V185_I18N__.t === "function") {
      return window.__V185_I18N__.t(key, vars);
    }
    return key;
  }

  function getDurationProfile() {
    return document.querySelector("input[name='apollo_duration_profile']:checked")?.value || "15s";
  }

  function liveGateEnabled() {
    return Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
  }

  function buildPayload(liveEnabled) {
    return {
      duration_profile: getDurationProfile(),
      live_enabled: !!liveEnabled,
      avatar_image_key: (document.getElementById("apollo-image-url")?.value || "").trim(),
      reference_video_key: "static/demo/demo_ref.mp4",
      prompt: (document.getElementById("apollo-prompt")?.value || "").trim(),
    };
  }

  async function apolloAvatarCreateTask() {
    const payload = buildPayload(false);
    const res = await fetch("/api/apollo/avatar/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch (_) {}
    if (!res.ok) {
      throw new Error(data?.detail || text || `HTTP ${res.status}`);
    }
    return data;
  }

  async function apolloAvatarGenerate(taskId, live) {
    const payload = buildPayload(!!live);
    const res = await fetch(`/api/apollo/avatar/${encodeURIComponent(taskId)}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch (_) {}
    if (!res.ok) {
      throw new Error(data?.detail || text || `HTTP ${res.status}`);
    }
    return data;
  }

  function apolloAvatarRenderResult(resp) {
    const out = document.getElementById("apollo-result");
    if (!out) return;
    const finalUrl = resp?.final_video_key || "";
    out.classList.remove("error");
    out.textContent = JSON.stringify(resp, null, 2);

    if (!finalUrl) return;
    const existing = document.getElementById("apollo-output-video");
    if (existing) existing.remove();
    const video = document.createElement("video");
    video.id = "apollo-output-video";
    video.controls = true;
    video.className = "preview-media";
    video.style.marginTop = "8px";
    video.src = finalUrl.startsWith("/") || finalUrl.startsWith("http") ? finalUrl : `/${finalUrl}`;
    out.parentElement?.appendChild(video);
  }

  function setLiveButtonState() {
    const liveBtn = document.getElementById("apollo-generate-live-btn");
    const liveHint = document.getElementById("apollo-live-disabled-hint");
    const liveToggle = document.getElementById("apollo-live-toggle");
    if (!liveBtn || !liveHint || !liveToggle) return;
    const enabled = liveGateEnabled();
    liveBtn.disabled = !enabled || !liveToggle.checked;
    liveHint.classList.toggle("hidden", enabled);
  }

  function bindApolloAvatar() {
    if (Number(window.__APOLLO_AVATAR_ENABLED__ || 0) !== 1) return;
    const panel = document.getElementById("apollo-avatar-panel");
    const openBtn = document.getElementById("apollo-open-btn");
    const createBtn = document.getElementById("apollo-create-btn");
    const demoBtn = document.getElementById("apollo-generate-demo-btn");
    const liveBtn = document.getElementById("apollo-generate-live-btn");
    const liveToggle = document.getElementById("apollo-live-toggle");
    const imageInput = document.getElementById("apollo-image-url");
    const imagePreview = document.getElementById("apollo-image-preview");
    const output = document.getElementById("apollo-result");
    let currentTaskId = "";

    if (openBtn && panel) {
      openBtn.addEventListener("click", function () {
        panel.classList.toggle("hidden");
      });
    }
    if (imageInput && imagePreview) {
      imageInput.addEventListener("change", function () {
        imagePreview.src = imageInput.value.trim() || "/static/demo/demo_avatar.jpg";
      });
    }
    if (liveToggle) {
      liveToggle.addEventListener("change", setLiveButtonState);
    }
    setLiveButtonState();

    if (createBtn) {
      createBtn.addEventListener("click", async function () {
        if (output) output.textContent = t("label.submit.status.submitting");
        try {
          const data = await apolloAvatarCreateTask();
          currentTaskId = data?.task_id || "";
          if (output) {
            output.classList.remove("error");
            output.textContent = JSON.stringify(data, null, 2);
          }
        } catch (err) {
          if (output) {
            output.classList.add("error");
            output.textContent = String(err && err.message ? err.message : err);
          }
        }
      });
    }

    if (demoBtn) {
      demoBtn.addEventListener("click", async function () {
        if (!currentTaskId) {
          if (output) output.textContent = t("apollo_avatar_create_task");
          return;
        }
        if (output) output.textContent = t("label.submit.status.submitting");
        try {
          const data = await apolloAvatarGenerate(currentTaskId, false);
          apolloAvatarRenderResult(data);
        } catch (err) {
          if (output) {
            output.classList.add("error");
            output.textContent = String(err && err.message ? err.message : err);
          }
        }
      });
    }

    if (liveBtn) {
      liveBtn.addEventListener("click", async function () {
        if (!liveGateEnabled()) {
          if (output) output.textContent = t("apollo_avatar_live_disabled_hint");
          return;
        }
        if (!currentTaskId) {
          if (output) output.textContent = t("apollo_avatar_create_task");
          return;
        }
        if (output) output.textContent = t("label.submit.status.submitting");
        try {
          const data = await apolloAvatarGenerate(currentTaskId, true);
          apolloAvatarRenderResult(data);
        } catch (err) {
          if (output) {
            output.classList.add("error");
            output.textContent = String(err && err.message ? err.message : err);
          }
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindApolloAvatar);
  } else {
    bindApolloAvatar();
  }

  window.apolloAvatarCreateTask = apolloAvatarCreateTask;
  window.apolloAvatarGenerate = apolloAvatarGenerate;
  window.apolloAvatarRenderResult = apolloAvatarRenderResult;
})();

