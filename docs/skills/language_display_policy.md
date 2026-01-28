# Language Display Policy (v1.85)

## Purpose
Standardize how UI text is presented across Workbench, Publish Hub, and Tools Hub to avoid mixed-language drift and operator confusion.

## Roles of Languages
- Chinese (ZH): Management language
  - Used for operational administration, SOP, and internal coordination.
- Burmese (MM): Usage language
  - Used for frontline operator execution and copy delivery to market.
- English (EN): Technical / functional language
  - Used for route-like labels, function names, and cross-team technical communication.
  - Should not dominate operator-facing UI.

## Display Rules
1. Operator UI uses tab-based locale (ZH or MM), not paired labels.
2. EN appears only when it improves cross-team clarity.
3. Avoid triple-language in a single label.
4. Tab labels must be consistent across pages.
5. Language tabs must not change URLs, data binding, or operator inputs.

## Implementation Guidance (Template-based)
- Use `data-i18n` keys with the locale tabs (`ui.locale`) to swap text.
- Keep default locale as ZH; allow switching to MM via tabs.
- Do not render paired labels in the same line.

## QA Checklist
- No page shows mixed-language paired labels.
- Tabs switch locale without reload.
- Publish Hub, Workbench, Tools Hub share the same tab locale behavior.
