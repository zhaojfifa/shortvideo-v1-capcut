# v1.8 Ops Baseline

## Scope
Operational expectations for v1.8 pack generation and download. This is not a spec for v1.7.

## Entry points (current)
- Pack generation: `POST /v1/pack`
- Pack download: `GET /v1/tasks/{task_id}/pack`

## Storage assumptions
- v1.8 pack is uploaded to object storage using `pack_key`.
- `pack_key` is authoritative; `pack_path` is legacy fallback.
- Object key format for v1.8 pack (current): `packs/{task_id}/capcut_pack.zip`

## Download behavior
- Returns `302` redirect to a presigned URL if the object exists.
- If `pack_key` missing, fallback to `pack_path`.
- If neither key exists or object missing, return `404`.

## Pack status
- `pack_status="ready"` implies the pack object exists and is downloadable.
- For ops, validate by checking object existence via storage (not by local zip path).

## Validation checklist
1) `POST /v1/pack` returns `pack_key`, `download_url`, `files[]`.
2) Object exists at `pack_key`.
3) `GET /v1/tasks/{task_id}/pack` returns 302 to the same object.
4) ZIP content matches `docs/v1.8/pack_spec.md`.
