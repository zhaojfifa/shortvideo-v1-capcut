(function () {
  const STORAGE_KEY = "ui.locale";
  const LOCALES = ["zh-CN", "my-MM"];

  const dict = {
    "zh-CN": {
      "ui.lang.zh": "中文",
      "ui.lang.mm": "မြန်မာ",
      "ui.common.search": "搜索",
      "ui.common.open": "打开",
      "ui.common.back": "返回",
      "ui.common.copy": "复制",
      "ui.common.download": "下载",
      "ui.workbench.title": "工作台",
      "ui.tasks.title": "任务",
      "ui.tasks.new": "新建任务",
      "ui.tasks.board": "任务看板",
      "ui.publish.title": "发布中心",
      "ui.publish.deliverables": "交付物",
      "ui.publish.copybundle": "文案包",
      "ui.publish.sop": "SOP",
      "ui.publish.archive": "归档",
      "ui.tools.title": "工具中心",
      "ui.tools.categories": "工具分类",
      "ui.tools.filters": "筛选",
      "ui.tools.detail": "工具详情"
    },
    "my-MM": {
      "ui.lang.zh": "中文",
      "ui.lang.mm": "မြန်မာ",
      "ui.common.search": "ရှာဖွေ",
      "ui.common.open": "ဖွင့်ရန်",
      "ui.common.back": "ပြန်သွား",
      "ui.common.copy": "ကူးယူ",
      "ui.common.download": "ဒေါင်းလုပ်",
      "ui.workbench.title": "အလုပ်ခုံ",
      "ui.tasks.title": "လုပ်ငန်းများ",
      "ui.tasks.new": "လုပ်ငန်းအသစ်",
      "ui.tasks.board": "လုပ်ငန်းဘုတ်",
      "ui.publish.title": "ထုတ်ဝေမှု",
      "ui.publish.deliverables": "ပို့ဆောင်မှု",
      "ui.publish.copybundle": "စာသားအစု",
      "ui.publish.sop": "လုပ်ထုံးလုပ်နည်း",
      "ui.publish.archive": "မှတ်တမ်းတင်",
      "ui.tools.title": "ကိရိယာများ",
      "ui.tools.categories": "အမျိုးအစားများ",
      "ui.tools.filters": "စစ်ထုတ်",
      "ui.tools.detail": "အသေးစိတ်"
    }
  };

  function getLocale() {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && LOCALES.includes(v)) return v;
    return "zh-CN";
  }

  function setLocale(locale) {
    if (!LOCALES.includes(locale)) return;
    localStorage.setItem(STORAGE_KEY, locale);
    applyLocale(locale);
    document.documentElement.setAttribute("data-locale", locale);
    document.querySelectorAll("[data-lang-tab]").forEach((el) => {
      el.classList.toggle("active", el.getAttribute("data-lang-tab") === locale);
    });
  }

  function t(locale, key) {
    return (dict[locale] && dict[locale][key]) || (dict["zh-CN"] && dict["zh-CN"][key]) || key;
  }

  function applyLocale(locale) {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      el.textContent = t(locale, key);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      el.setAttribute("placeholder", t(locale, key));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      el.setAttribute("title", t(locale, key));
    });
  }

  function boot() {
    const locale = getLocale();
    document.documentElement.setAttribute("data-locale", locale);
    applyLocale(locale);
    document.querySelectorAll("[data-lang-tab]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        setLocale(el.getAttribute("data-lang-tab"));
      });
    });
    document.querySelectorAll("[data-lang-tab]").forEach((el) => {
      el.classList.toggle("active", el.getAttribute("data-lang-tab") === locale);
    });
  }

  window.__V185_I18N__ = { getLocale, setLocale, applyLocale, dict };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
