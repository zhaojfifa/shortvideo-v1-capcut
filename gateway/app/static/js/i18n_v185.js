(function () {
  const COOKIE_NAME = "ui_locale";
  const PARAM_NAME = "ui_locale";

  function getPayload() {
    return window.__I18N__ || { locale: "zh", supported: ["zh", "mm"], dict: { zh: {}, mm: {} } };
  }

  function getSupported() {
    const payload = getPayload();
    return payload.supported || ["zh", "mm"];
  }

  function getQueryLocale() {
    const qs = new URLSearchParams(window.location.search || "");
    const v = (qs.get(PARAM_NAME) || "").toLowerCase();
    return v;
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

  function t(key, vars) {
    const payload = getPayload();
    const locale = resolveLocale();
    const table = (payload.dict && payload.dict[locale]) || {};
    const zh = (payload.dict && payload.dict.zh) || {};
    let text = table[key] || zh[key] || key;
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
