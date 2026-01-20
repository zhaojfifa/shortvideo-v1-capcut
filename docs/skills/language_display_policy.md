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
1. Default pattern for operator UI is: **ZH + MM**
   - Example: `交付物 / ပေးပို့ချက်`
2. EN appears only when it improves cross-team clarity:
   - Example: `交付物 / Deliverables` (acceptable for tab label)
3. Avoid triple-language in a single label unless it is a header or a help tooltip.
4. Tab labels must be consistent across pages:
   - Publish Hub and Workbench should use the same label pairing style.
5. “Toggle language” is optional; when present:
   - Toggle switches *secondary language layer* (e.g., show/hide MM),
   - Must not change URLs, data binding, or operator inputs.

## Implementation Guidance (Template-based)
- Use paired strings and render as `Primary / Secondary`.
- Keep the primary language stable per page (ZH recommended).
- All key operator actions (buttons) should include ZH; MM may be secondary.

## QA Checklist
- No page shows mixed patterns (e.g., some tabs ZH+MM, others ZH+EN) unless explicitly justified.
- Publish Hub: all 4 tabs follow the same pairing.
- Workbench: key section headers match Publish Hub’s pairing style.
