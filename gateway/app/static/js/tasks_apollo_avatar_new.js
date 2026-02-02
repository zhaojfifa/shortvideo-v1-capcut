(function () {
  function $(id) {
    return document.getElementById(id);
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
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
    return data || {};
  }

  function getDurationProfile() {
    return document.querySelector("input[name='duration_profile']:checked")?.value || "15s";
  }

  function getPayload(isDemo) {
    const liveChecked = !!$("live_enabled")?.checked;
    const gateOn = Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
    return {
      duration_profile: getDurationProfile(),
      live_enabled: isDemo ? false : (gateOn && liveChecked),
      avatar_image_key: $("avatar_image_url")?.value?.trim() || "",
      reference_video_key: $("ref_video_url")?.value?.trim() || "",
      prompt: $("prompt")?.value?.trim() || "",
    };
  }

  function setResult(value, isError) {
    const box = $("result");
    if (!box) return;
    box.classList.toggle("error", !!isError);
    box.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }

  let currentTaskId = null;

  async function onCreate(isDemo) {
    const payload = getPayload(isDemo);
    const result = await postJson("/api/apollo/avatar/tasks", payload);
    currentTaskId = result.task_id || result.id || null;
    setResult(result, false);
  }

  async function onGenerate() {
    if (!currentTaskId) {
      throw new Error("Create task first");
    }
    const payload = getPayload(false);
    const result = await postJson(`/api/apollo/avatar/${encodeURIComponent(currentTaskId)}/generate`, payload);
    setResult(result, false);
  }

  function bind() {
    const gateOn = Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
    const hint = $("apollo-live-disabled-hint");
    if (hint) {
      hint.style.display = gateOn ? "none" : "block";
    }

    const avatarInput = $("avatar_image_url");
    const avatarPreview = $("avatar_preview");
    if (avatarInput && avatarPreview) {
      avatarInput.addEventListener("change", () => {
        avatarPreview.src = avatarInput.value.trim() || "/static/demo/demo_avatar.jpg";
      });
    }

    $("btn_create")?.addEventListener("click", async () => {
      try {
        await onCreate(false);
      } catch (err) {
        setResult(err.message || String(err), true);
      }
    });

    $("btn_create_demo")?.addEventListener("click", async () => {
      try {
        await onCreate(true);
      } catch (err) {
        setResult(err.message || String(err), true);
      }
    });

    $("btn_generate")?.addEventListener("click", async () => {
      try {
        await onGenerate();
      } catch (err) {
        setResult(err.message || String(err), true);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();

