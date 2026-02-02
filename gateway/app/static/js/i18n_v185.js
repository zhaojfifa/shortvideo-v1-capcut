(function () {
  const COOKIE_NAME = "ui_locale";
  const PARAM_NAME = "ui_locale";
  const CLIENT_DICT = {
    zh: {
      scn_apollo_avatar_title: "ApolloAvatar",
      scn_apollo_avatar_desc: "数字人跟随生成",
      apollo_avatar_duration: "时长档位",
      apollo_avatar_15s: "15秒",
      apollo_avatar_30s: "30秒",
      apollo_avatar_live_toggle: "Live（计费）",
      apollo_avatar_live_hint: "开启 Live 会调用外部视频模型并产生费用；默认仅展示 demo，不计费。",
      apollo_avatar_char_image: "角色图",
      apollo_avatar_prompt: "提示词",
      apollo_avatar_ref_video: "参考视频",
      apollo_avatar_create_task: "创建任务",
      apollo_avatar_generate_demo: "生成（Demo）",
      apollo_avatar_generate_live: "生成（Live）",
      apollo_avatar_live_disabled_hint: "当前环境未开启 Live gate。",
      tab_digital_human: "数字人",
      tab_hot_follow: "热点跟随",
      hot_follow_title: "热点跟随",
      coming_soon: "敬请期待。",
      seed: "Seed（可选）",
      new_digital_human: "新建数字人",
    },
    mm: {
      scn_apollo_avatar_title: "ApolloAvatar",
      scn_apollo_avatar_desc: "Avatar follow generation",
      apollo_avatar_duration: "ကြာချိန်",
      apollo_avatar_15s: "15 စက္ကန့်",
      apollo_avatar_30s: "30 စက္ကန့်",
      apollo_avatar_live_toggle: "Live (ကျသင့်)",
      apollo_avatar_live_hint: "Live ကိုဖွင့်လျှင် ကုန်ကျစရိတ်ရှိနိုင်သည်၊ မူလအနေဖြင့် demo သာ ပြပါမည်။",
      apollo_avatar_char_image: "ဇာတ်ကောင်ပုံ",
      apollo_avatar_prompt: "Prompt",
      apollo_avatar_ref_video: "ရည်ညွှန်းဗီဒီယို",
      apollo_avatar_create_task: "Task ဖန်တီးမည်",
      apollo_avatar_generate_demo: "Generate (Demo)",
      apollo_avatar_generate_live: "Generate (Live)",
      apollo_avatar_live_disabled_hint: "Live gate ကိုမဖွင့်ထားသေးပါ။",
      tab_digital_human: "Digital Human",
      tab_hot_follow: "Hot Follow",
      hot_follow_title: "Hot Follow",
      coming_soon: "Coming soon.",
      seed: "Seed",
      new_digital_human: "New Digital Human",
    },
  };

  function getPayload() {
    return window.__I18N__ || { locale: "zh", supported: ["zh", "mm"], dict: { zh: {}, mm: {} } };
  }

  function getSupported() {
    const payload = getPayload();
    return payload.supported || ["zh", "mm"];
  }

  function getQueryLocale() {
    const qs = new URLSearchParams(window.location.search || "");
    return (qs.get(PARAM_NAME) || "").toLowerCase();
  }

  function getCookieLocale() {
    const m = document.cookie.match(new RegExp("(?:^|; )" + COOKIE_NAME + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function setCookie(locale) {
    const maxAge = 60 * 60 * 24 * 365;
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(locale)}; path=/; max-age=${maxAge}`;
  }

  function setQueryLocale(locale) {
    const url = new URL(window.location.href);
    url.searchParams.set(PARAM_NAME, locale);
    window.location.href = url.toString();
  }

  function resolveLocale() {
    const payload = getPayload();
    const supported = getSupported();
    const queryLocale = getQueryLocale();
    if (supported.includes(queryLocale)) return queryLocale;
    const cookieLocale = getCookieLocale();
    if (supported.includes(cookieLocale)) return cookieLocale;
    if (supported.includes(payload.locale)) return payload.locale;
    return "zh";
  }

  function getFallbacks() {
    const payload = getPayload();
    return payload.fallbacks || {
      mm: ["mm", "zh"],
      zh: ["zh"],
    };
  }

  function t(key, vars) {
    const payload = getPayload();
    const locale = resolveLocale();
    const dict = payload.dict || {};
    const fallbacks = getFallbacks();
    const chain = fallbacks[locale] || [locale, "zh"];
    let text;
    for (const loc of chain) {
      const table = dict[loc] || {};
      if (table[key]) {
        text = table[key];
        break;
      }
      const clientTable = CLIENT_DICT[loc] || {};
      if (clientTable[key]) {
        text = clientTable[key];
        break;
      }
    }
    if (!text) {
      text = `【MISSING:${key}】`;
    }
    if (vars && typeof text === "string") {
      Object.keys(vars).forEach((k) => {
        text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(vars[k]));
      });
    }
    return text;
  }

  function applyLocale(locale) {
    document.documentElement.setAttribute("data-locale", locale);
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      el.textContent = t(key);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      el.setAttribute("placeholder", t(key));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      el.setAttribute("title", t(key));
    });
  }

  function boot() {
    const locale = resolveLocale();
    applyLocale(locale);
    document.querySelectorAll("[data-lang-tab]").forEach((el) => {
      el.classList.toggle("active", el.getAttribute("data-lang-tab") === locale);
      el.addEventListener("click", (e) => {
        e.preventDefault();
        const target = el.getAttribute("data-lang-tab");
        if (!target) return;
        setCookie(target);
        setQueryLocale(target);
      });
    });
  }

  window.__V185_I18N__ = { t };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
