# UI Language Skill: Publish Hub (ZH/MM)

## Purpose
Define a single, reusable language configuration mechanism for UI pages that need bilingual labels (Chinese + Burmese) without changing business logic or API contracts.

This skill standardizes:
- storage keys
- default language selection
- DOM patterns for bilingual labels
- CSS visibility rules
- minimal JS helpers

## Supported Languages
- `zh` (Chinese)
- `mm` (Burmese)

## Storage
- localStorage key: `ui_lang_publish_hub`
- allowed values: `zh`, `mm`

## Default Language Resolution (priority)
1) localStorage `ui_lang_publish_hub`
2) server-provided `ui_lang` (if present in task/publish_hub response)
3) fallback: `zh`

## DOM Pattern
Use a single page-level attribute to control visibility:

- set on `<body>` (recommended): `data-lang="zh"` or `data-lang="mm"`

Wrap bilingual labels with two spans:

```html
<span class="i18n zh">发布归档</span>
<span class="i18n mm">...</span>
```

Do not duplicate toggles per tab. One toggle controls the whole page.

CSS Rules
```
[data-lang="zh"] .i18n.mm { display: none; }
[data-lang="mm"] .i18n.zh { display: none; }
```

JS Helpers (Minimal)
```
const LANG_KEY = "ui_lang_publish_hub";

function resolveLang(serverLang) {
  const saved = localStorage.getItem(LANG_KEY);
  return saved || serverLang || "zh";
}

function applyLang(lang) {
  document.body.dataset.lang = lang;
  localStorage.setItem(LANG_KEY, lang);
}
```

Interaction Rules

Language switching MUST NOT modify or reset user-entered content.

Language switching affects labels and hints only.

URLs, IDs, download codes are language-agnostic and must not be duplicated.

Page Integration Checklist

- single toggle rendered once per page
- attribute data-lang is applied at page load
- all bilingual labels use .i18n.zh + .i18n.mm
- refresh preserves language selection
- no backend changes required
