# PR-3 ApolloAvatar Stitch-Only (WAN2.6 Flash)

## Spec
- 15s => 5s x 3 segments
- 30s => 10s x 3 segments
- Provider: WAN v2.6 image-to-video flash (fal)
- Flow: generate segments -> stitch -> final

## Env Vars
- ENABLE_APOLLO_AVATAR
- APOLLO_AVATAR_LIVE_ENABLED
- APOLLO_AVATAR_PROVIDER (default: fal_wan26_flash)
- FAL_KEY
- FAL_WAN26_FLASH_MODEL (default: wan/v2.6/image-to-video/flash)
- DEMO_ASSET_BASE_URL (optional CDN base for previews)

## Acceptance
- UI: /tasks/apollo-avatar/new renders, accepts 15/30 + seed + prompt
- List: /tasks?kind=apollo_avatar only shows apollo_avatar
- Demo mode: no external API calls
- Live mode: requires gates, generates 3 segments, stitches, uploads final + manifest
- Suitcase /tasks/new unchanged
