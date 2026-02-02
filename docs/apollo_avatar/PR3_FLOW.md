# ApolloAvatar PR-3 Flow (Contracts + Non-Interference Rules)

## Goal
Turn ApolloAvatar into a real scenario task:
- User uploads: (1) avatar portrait image, (2) reference/driving video
- System generates video: 15s or 30s delivery
- Internally: fixed 3 segments
  - 15s = 5s × 3
  - 30s = 10s × 3
- Outputs:
  - segments[] + segment_manifest.json for editability (CapCut pack)
  - final.mp4 stitched for base pipeline (subtitles/translation/dub/pack)
- Provider is swappable; task/base pipeline contracts must not change.

## Hard Constraints
- Delivery lengths remain ONLY 15/30 for now (cost control).
- Non-interference:
  - Suitcase tasks and pages unchanged.
  - ApolloAvatar has its own list + new page.
  - Provider layer is isolated behind a port.
- Demo assets should be served from CDN (Cloudflare/R2), not git repo.

## URLs / UI
- List: /tasks?kind=apollo_avatar (shows ONLY apollo_avatar tasks)
- New:  /tasks/apollo-avatar/new (ApolloAvatar-only form)
- “任务” button must NOT refresh current page; rename to “热点跟随” (placeholder).

## Data Contract (Task meta)
category_key: apollo_avatar
meta:
  duration_sec: 15|30
  segment_sec: 5|10
  segments: 3
  seed: optional int
  prompt: string
  avatar_asset:
    kind: image
    url: https://cdn.../...
  ref_video_asset:
    kind: video
    url: https://cdn.../...
  provider:
    name: fal_wan26_flash (default)
    model: wan/v2.6/image-to-video/flash
  artifacts:
    segments_dir: r2://...
    final_video: https://cdn.../final.mp4
    manifest: https://cdn.../segment_manifest.json

## Pipeline Mapping
1) Upload assets -> store in R2 -> return CDN URLs
2) Generate segments (provider):
   for i in 1..3:
     generate segment_i.mp4 (duration = segment_sec)
3) Stitch:
   concat segments -> final.mp4
4) Base pipeline:
   final.mp4 -> subtitles -> translation -> dub -> pack (existing steps)
5) CapCut pack:
   include final.mp4 + segments + manifest for editing

## Provider Port (stable)
interface VideoGenProvider:
  generate_segment(
    avatar_image_url: str,
    ref_video_url: str,
    prompt: str,
    duration_sec: int,
    seed: Optional[int],
  ) -> GeneratedVideo(url: str, bytes?: Optional[bytes], meta: dict)

Provider implementations must not leak into routers/templates.
