# UI Language Policy (v1.85+)

## Purpose
This project uses a 3-layer language policy to keep engineering collaboration stable while ensuring operators can execute reliably.

## Language Roles
- English (EN): default engineering language
  - Code, variables, API fields, logs, commit messages, technical docs.
- Chinese (ZH): management language
  - Admin/operator-facing field labels, internal process naming, management SOP guidance.
- Burmese (MM): operator execution language
  - Operator-facing instructions and critical UI labels for daily use.

## UI Display Rules (Publish Hub)
- The Publish Hub UI must display **ZH + MM side-by-side** (ZH first, MM second).
- English should not appear in UI labels unless strictly necessary (e.g., brand/model names).
- Do not implement per-tab language switching in v1.85. Use consistent bilingual strings.
- Keep layout and APIs stable; changes should be limited to text rendering.

## Implementation Pattern
Use a small helper in the Publish Hub template:

- `bi(zh, mm)` returns "zh / mm" when both exist.
- Apply to:
  - Tab labels
  - Section titles
  - Field labels
  - Helper texts
  - Button captions

## QA Checklist
- All 4 tabs (SOP / Copy Bundle / Deliverables / Archive) show bilingual labels consistently.
- No toggle suggests single-language mode.
- No endpoint or data model changes.
