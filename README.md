# ShortVideo Pack Pipeline

This repo runs the ShortVideo pipeline (parse -> subtitles -> dub -> pack) and serves operator-facing APIs and pages for generating and downloading CapCut/YouCut-ready packs. v1.7 remains supported as a compatibility path; v1.8 is the active ops baseline.


## Ops Quick Links (v1.8)

- Ops handoff contract: docs/ops/v1.8_ops_handoff.md
- YouCut SOP (?? + ??????): docs/ops/youcut_sop_zh_mm.md
- Scenes spec: docs/v1.8/scenes_spec.md
## Ops baseline (v1.8)

Flow: Task -> Pack -> Download URL
- Generate pack: `POST /v1/pack` (stores `pack_key` + `pack_status`)
- Download pack: `GET /v1/tasks/{task_id}/pack` (redirects to a presigned URL)
- Expected ZIP layout: `deliver/packs/<task_id>/...` (see pack spec)

## Quick links
- `docs/overview.md`
- `docs/v1.8/ops_baseline.md`
- `docs/v1.8/pack_spec.md`
- `docs/architecture/hexagonal.md`

## v1.7 note
Compatibility path remains unchanged. Reference:
- `docs/v1.7_acceptance_day5.md`
- `docs/v1.7_pack_validation.md`
- `docs/v1.7_runtime_notes.md`

## Baseline tag
`v1.8-p0-pack-baseline`