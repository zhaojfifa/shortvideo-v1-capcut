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

  async function postForm(url, formData) {
    const res = await fetch(url, {
      method: "POST",
      body: formData,
    });
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch (_) {}
    if (!res.ok) {
      throw new Error(data?.detail || text || `HTTP ${res.status}`);
    }
    return data || {};
  }

  function getTargetDurationSec() {
    const value = document.querySelector("input[name='duration_profile']:checked")?.value || "15s";
    return value === "30s" ? 30 : 15;
  }

  function getSeed() {
    const seedRaw = $("seed")?.value?.trim();
    const seedVal = seedRaw ? Number(seedRaw) : null;
    return Number.isFinite(seedVal) ? seedVal : null;
  }

  function setResult(value, isError) {
    const box = $("result");
    if (!box) return;
    box.classList.toggle("error", !!isError);
    box.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  }

  let currentTaskId = null;
  const state = {
    avatarFile: null,
    refVideoFile: null,
  };

  function buildCreateFormData(liveEnabled) {
    if (!state.avatarFile) {
      throw new Error("Avatar image is required");
    }
    if (!state.refVideoFile) {
      throw new Error("Reference video is required");
    }
    const form = new FormData();
    form.append("avatar_file", state.avatarFile);
    form.append("ref_video_file", state.refVideoFile);
    form.append("duration_sec", String(getTargetDurationSec()));
    form.append("prompt", $("prompt")?.value?.trim() || "");
    const seedVal = getSeed();
    if (seedVal !== null) {
      form.append("seed", String(seedVal));
    }
    form.append("live_enabled", liveEnabled ? "true" : "false");
    return form;
  }

  async function onCreate(isDemo) {
    const gateOn = Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
    const liveChecked = !!$("live_enabled")?.checked;
    const liveEnabled = isDemo ? false : (gateOn && liveChecked);
    const form = buildCreateFormData(liveEnabled);
    const result = await postForm("/api/apollo/avatar/tasks", form);
    currentTaskId = result.task_id || result.id || null;
    setResult(result, false);
  }

  async function onGenerate(isDemo) {
    if (!currentTaskId) {
      await onCreate(isDemo);
      if (!currentTaskId) {
        throw new Error("Create task first");
      }
    }
    const result = await postJson(`/api/apollo/avatar/${encodeURIComponent(currentTaskId)}/generate`, null);
    setResult(result, false);
  }

  function bind() {
    const gateOn = Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
    const hint = $("apollo-live-disabled-hint");
    if (hint) {
      hint.style.display = gateOn ? "none" : "block";
    }
    const genBtn = $("btn_generate");
    if (genBtn) {
      genBtn.disabled = !gateOn;
    }

    const demoBase = (window.__DEMO_ASSET_BASE_URL__ || "").replace(/\/+$/, "");
    const demoAvatar = demoBase ? `${demoBase}/apollo_avatar/demo_avatar.png` : "/static/demo/demo_avatar.png";
    const demo15 = demoBase ? `${demoBase}/apollo_avatar/demo_15.mp4` : "/static/demo/demo_15.mp4";
    const demo30 = demoBase ? `${demoBase}/apollo_avatar/demo_30.mp4` : "/static/demo/demo_30.mp4";

    const avatarPreview = $("avatar_preview");
    const refPreview = $("ref_video_preview");
    const setDemoVideo = () => {
      if (!refPreview) return;
      const demoSrc = getTargetDurationSec() === 30 ? demo30 : demo15;
      let src = refPreview.querySelector("source");
      if (!src) {
        src = document.createElement("source");
        src.setAttribute("type", "video/mp4");
        refPreview.appendChild(src);
      }
      if (!src.getAttribute("src")) {
        src.setAttribute("src", demoSrc);
        refPreview.load();
      }
    };

    if (avatarPreview && !avatarPreview.getAttribute("src")) {
      avatarPreview.src = demoAvatar;
    }
    setDemoVideo();

    const avatarInput = $("avatar_file");
    if (avatarInput && avatarPreview) {
      avatarInput.addEventListener("change", () => {
        const file = avatarInput.files && avatarInput.files[0];
        state.avatarFile = file || null;
        if (file) {
          avatarPreview.src = URL.createObjectURL(file);
        }
      });
    }

    const refInput = $("ref_video_file");
    if (refInput && refPreview) {
      refInput.addEventListener("change", () => {
        const file = refInput.files && refInput.files[0];
        state.refVideoFile = file || null;
        if (file) {
          const url = URL.createObjectURL(file);
          let src = refPreview.querySelector("source");
          if (!src) {
            src = document.createElement("source");
            src.setAttribute("type", "video/mp4");
            refPreview.appendChild(src);
          }
          src.setAttribute("src", url);
          refPreview.load();
        }
      });
    }
    document.querySelectorAll("input[name='duration_profile']").forEach((el) => {
      el.addEventListener("change", () => {
        if (!state.refVideoFile) {
          setDemoVideo();
        }
      });
    });

    $("btn_create")?.addEventListener("click", async () => {
      try {
        await onCreate(false);
      } catch (err) {
        setResult(err.message || String(err), true);
      }
    });

    $("btn_create_demo")?.addEventListener("click", async () => {
      try {
        await onGenerate(true);
      } catch (err) {
        setResult(err.message || String(err), true);
      }
    });

    $("btn_generate")?.addEventListener("click", async () => {
      try {
        const gateOn = Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
        if (!gateOn) {
          throw new Error("Live is disabled");
        }
        if (!$("live_enabled")?.checked) {
          throw new Error("Enable Live (billable) to generate live");
        }
        await onGenerate(false);
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

