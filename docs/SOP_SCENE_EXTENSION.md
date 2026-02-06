# Scene Extension SOP (Publish Hub + Deliverables)

This SOP defines the minimal steps to add a new “scene” (ApolloAvatar, HotFollow, etc.)
without breaking the base pipeline or existing publish hub.

## Checklist (Must)
1) Add a scene-specific publish hub endpoint:
   - `GET /api/<scene>/{task_id}/publish_hub`
2) Ensure scene post pipeline uploads primary deliverables into ArtifactStorage:
   - Persist `publish_key` (and `publish_status`) on the task
3) Provide scene-specific deliverables mapping:
   - Return signed download URLs (via `/op/dl` or storage-signed URLs)
4) Frontend dispatch:
   - Publish page chooses endpoint based on `task.kind` / `task.category_key`
5) Acceptance:
   - `/api/tasks/{id}/publish_hub` unchanged for base tasks
   - `/api/<scene>/{id}/publish_hub` works for scene tasks
   - Deliverables URLs are not local filesystem paths

## Template Pattern (ApolloAvatar Example)

- Scene publish hub builder:
  - `gateway/app/scenes/apollo_avatar/publish_hub.py`
  - `build_apollo_avatar_publish_hub(task)`

- Scene publish hub route:
  - `gateway/app/routers/apollo_avatar.py`
  - `GET /api/apollo/avatar/{task_id}/publish_hub`

- Frontend publish page dispatch:
  - `gateway/app/templates/task_publish_hub.html`
  - Choose API endpoint based on `task.category_key` or `task.kind`

## Minimum Deliverables
- `edit_bundle_zip`: publish bundle zip (signed URL)
- `pack_zip`: final pack zip (signed URL)
- `mm_srt`, `mm_audio` (optional)

## Notes
- Do NOT add conditional logic inside `/api/tasks/{task_id}/publish_hub`.
- Keep scene logic isolated in `gateway/app/scenes/<scene>/`.
