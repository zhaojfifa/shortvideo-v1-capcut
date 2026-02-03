(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function normalizeDemoRoot(rawBase) {
    const base0 = String(rawBase || "").trim().replace(/\/+$/, "");
    if (!base0) return "";
    const base1 = base0.replace(/\/apollo_avatar\/[^/]+\.(png|jpg|jpeg|mp4)$/i, "/apollo_avatar");
    if (base1.endsWith("/apollo_avatar") || base1.endsWith("apollo_avatar")) return base1;
    return `${base1}/apollo_avatar`;
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

  function getPayload(isDemo) {
    const liveChecked = !!$("live_enabled")?.checked;
    const gateOn = Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
    const seedVal = getSeed();
    const demoRoot = normalizeDemoRoot(window.__DEMO_ASSET_BASE_URL__);
    const demoAvatar = demoRoot ? `${demoRoot}/demo_avatar.png` : "";
    const demoRef15 = demoRoot ? `${demoRoot}/demo_15.mp4` : "";
    return {
      target_duration_sec: getTargetDurationSec(),
      live_enabled: isDemo ? false : (gateOn && liveChecked),
      avatar_image_url: isDemo ? demoAvatar : ($("avatar_image_url")?.value?.trim() || ""),
      reference_video_url: isDemo ? demoRef15 : ($("ref_video_url")?.value?.trim() || ""),
      prompt: $("prompt")?.value?.trim() || "",
      seed: Number.isFinite(seedVal) ? seedVal : null,
    };
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

  async function fetchAsFile(url, filename, mime) {
    if (!url) {
      throw new Error("Demo asset URL missing");
    }
    const res = await fetch(url, { mode: "cors" });
    if (!res.ok) {
      throw new Error(`Failed to fetch demo asset: ${url}`);
    }
    const blob = await res.blob();
    return new File([blob], filename, { type: mime || blob.type || "application/octet-stream" });
  }

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
    if (isDemo && (!state.avatarFile || !state.refVideoFile)) {
      const root = normalizeDemoRoot(window.__DEMO_ASSET_BASE_URL__);
      const demoAvatar = root ? `${root}/demo_avatar.png` : "";
      const demoRef = root
        ? (getTargetDurationSec() === 30
            ? `${root}/demo_30.mp4`
            : `${root}/demo_15.mp4`)
        : "";
      state.avatarFile = state.avatarFile || await fetchAsFile(demoAvatar, "demo_avatar.png", "image/png");
      state.refVideoFile = state.refVideoFile || await fetchAsFile(demoRef, "demo_ref.mp4", "video/mp4");
    }
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
    const payload = getPayload(isDemo);
    const result = await postJson(`/api/apollo/avatar/${encodeURIComponent(currentTaskId)}/generate`, payload);
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

    const demoRoot = normalizeDemoRoot(window.__DEMO_ASSET_BASE_URL__);
    const demoAvatar = demoRoot ? `${demoRoot}/demo_avatar.png` : "";
    const demo15 = demoRoot ? `${demoRoot}/demo_15.mp4` : "";
    const demo30 = demoRoot ? `${demoRoot}/demo_30.mp4` : "";

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
      if (demoAvatar) {
        avatarPreview.src = demoAvatar;
      }
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

