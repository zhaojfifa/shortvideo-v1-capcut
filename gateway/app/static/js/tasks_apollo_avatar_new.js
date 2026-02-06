(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function normalizeDemoRoot(rawBase) {
    const base0 = String(rawBase || "").trim().replace(/\/+$/, "");
    if (!base0) return "";
    const base1 = base0.replace(/\/apollo_avatar\/[^/]+\.(png|jpg|jpeg|mp4)$/i, "/apollo_avatar");
    if (base1.endsWith("/apollo_avatar") || base1.endsWith("apollo_avatar")) {
      return base1.replace(/\/apollo_avatar$/, "");
    }
    return base1;
  }

  async function safeReadResponse(res) {
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (ct.includes("application/json")) {
      return { kind: "json", data: await res.json() };
    }
    const text = await res.text();
    return { kind: "text", data: text.slice(0, 4000) };
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const parsed = await safeReadResponse(res);
    if (!res.ok) {
      const msg = parsed.kind === "json"
        ? (parsed.data?.detail || parsed.data?.error || JSON.stringify(parsed.data))
        : parsed.data;
      const err = new Error(`HTTP ${res.status}: ${msg || res.statusText}`);
      err.status = res.status;
      err.payload = parsed.data;
      err.contentType = parsed.kind;
      throw err;
    }
    return parsed.kind === "json" ? parsed.data : { ok: true, raw: parsed.data };
  }

  async function postForm(url, formData) {
    const res = await fetch(url, {
      method: "POST",
      body: formData,
    });
    const parsed = await safeReadResponse(res);
    if (!res.ok) {
      const msg = parsed.kind === "json"
        ? (parsed.data?.detail || parsed.data?.error || JSON.stringify(parsed.data))
        : parsed.data;
      const err = new Error(`HTTP ${res.status}: ${msg || res.statusText}`);
      err.status = res.status;
      err.payload = parsed.data;
      err.contentType = parsed.kind;
      throw err;
    }
    return parsed.kind === "json" ? parsed.data : { ok: true, raw: parsed.data };
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
    const demoBase = normalizeDemoRoot(window.__DEMO_ASSET_BASE_URL__);
    const demoRoot = demoBase ? `${demoBase}/apollo_avatar` : "";
    const demoAvatar = demoRoot ? `${demoRoot}/demo_avatar.png` : "";
    const demoRef15 = demoRoot ? `${demoRoot}/demo_15.mp4` : "";
    return {
      target_duration_sec: getTargetDurationSec(),
      live: isDemo ? false : (gateOn && liveChecked),
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
  let busy = false;
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

  function setBusy(state) {
    busy = state;
    const btns = ["btn_create", "btn_create_demo", "btn_generate"]
      .map((id) => $(id))
      .filter(Boolean);
    btns.forEach((b) => {
      if (state) {
        b.setAttribute("data-prev-disabled", b.disabled ? "1" : "0");
        b.disabled = true;
      } else {
        const prev = b.getAttribute("data-prev-disabled");
        b.disabled = prev === "1";
        b.removeAttribute("data-prev-disabled");
      }
    });
  }

  async function onCreate(isDemo) {
    if (busy) return;
    setBusy(true);
    const gateOn = Number(window.__APOLLO_AVATAR_LIVE_ENABLED__ || 0) === 1;
    const liveChecked = !!$("live_enabled")?.checked;
    const liveEnabled = isDemo ? false : (gateOn && liveChecked);
    if (isDemo && (!state.avatarFile || !state.refVideoFile)) {
      const base = normalizeDemoRoot(window.__DEMO_ASSET_BASE_URL__);
      const root = base ? `${base}/apollo_avatar` : "";
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
    try {
      const result = await postForm("/api/apollo/avatar/tasks", form);
      currentTaskId = result.task_id || result.id || null;
      setResult(result, false);
      return result;
    } finally {
      setBusy(false);
    }
  }

  async function onGenerate(isDemo) {
    if (busy) return;
    setBusy(true);
    try {
      if (!currentTaskId) {
        await onCreate(isDemo);
        if (!currentTaskId) {
          throw new Error("Create task first");
        }
      }
      const payload = isDemo ? getPayload(true) : {
        live: true,
        prompt: $("prompt")?.value?.trim() || "",
        seed: getSeed(),
        force: false,
      };
      const result = await postJson(`/api/apollo/avatar/${encodeURIComponent(currentTaskId)}/generate`, payload);
      setResult(result, false);
    } catch (err) {
      const status = err?.status ? `status=${err.status}` : "";
      const msg = err?.payload ? JSON.stringify(err.payload, null, 2) : (err?.message || String(err));
      setResult(`Generate failed ${status}\n${msg}`.trim(), true);
      console.warn("ApolloAvatar generate failed", { status: err?.status, contentType: err?.contentType });
    } finally {
      setBusy(false);
    }
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

    const demoBase = normalizeDemoRoot(window.__DEMO_ASSET_BASE_URL__);
    const demoRoot = demoBase ? `${demoBase}/apollo_avatar` : "";
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

