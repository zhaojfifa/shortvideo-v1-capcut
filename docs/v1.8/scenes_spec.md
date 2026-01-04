# v1.8 Scenes Spec (scenes.zip + scenes_manifest.json)

This spec defines the v1.8 scenes artifact set produced for ops usage.
Primary goal: enable ?scene MSC? delivery without making pack.zip heavier.

## 1) Core Principle: Keep scenes.zip lightweight

scenes.zip MUST contain only scenes assets and documentation:
- scenes/scene_*/...
- scenes_manifest.json
- README.md

scenes.zip MUST NOT duplicate full assets already delivered in pack.zip:
- do not copy full raw video again
- do not copy full audio/subtitles sets already in pack.zip

## 2) Output Location (workspace)

Deliver root (frozen pattern):
- workspace/deliver/scenes/{task_id}/

Recommended structure inside:
- scenes/
  - scene_001/
    - video.mp4          # clean video slice (no burned-in subtitles)
    - audio.wav          # optional; include when available (recommended early)
    - subs.srt           # subtitle slice rebased to 0
    - scene.json         # per-scene manifest (static)
  - scene_002/...
- scenes_manifest.json    # machine-read
- README.md               # human-read (ops)
- scenes.zip              # zip of above

## 3) scenes_manifest.json (recommended schema)

Goals:
- machine usable
- supports future 1.9/2.0 semantic tags without changing v1.8 behavior

Example (minimal + extensible):

{
  "version": "1.8",
  "task_id": "task_xxx",
  "language": "mm",
  "source": {
    "raw_video": "deliver/packs/<task_id>/raw/raw.mp4",
    "subs_srt": "deliver/packs/<task_id>/subs/mm.srt"
  },
  "split_policy": {
    "engine": "faster-whisper",
    "model": "small",
    "mode": "time_strict",
    "min_scene_sec": 3.0,
    "max_scene_sec": 18.0,
    "silence_gap_sec": 0.6,
    "group_n_captions": 4
  },
  "scenes": [
    {
      "scene_id": "scene_001",
      "start": 12.40,
      "end": 18.90,
      "role": "unknown",
      "summary": "",
      "assets": {
        "video": "scenes/scene_001/video.mp4",
        "audio": "scenes/scene_001/audio.wav",
        "subs": "scenes/scene_001/subs.srt",
        "manifest": "scenes/scene_001/scene.json"
      }
    }
  ]
}

Notes:
- start/end are seconds relative to the raw video
- role/summary are optional placeholders for 1.9/2.0 tagging (do not change slicing in 1.8)

## 4) README.md (human-read) requirements

Ops should not be required to read JSON. README must include:
- how to download scenes.zip
- how to unzip
- how to preview quickly (open scene_*/video.mp4)
- how to use scenes as a ?material pool? in editors (YouCut/CapCut)
- a table listing each scene:
  - scene_id
  - start/end
  - file paths (video/audio/subs)

## 5) Storage (R2 key recommendation)

scenes.zip upload key:
- deliver/scenes/{task_id}/scenes.zip

Download endpoint semantics (contract):
- GET /v1/tasks/{task_id}/scenes -> 302 redirect to R2 presigned URL
- /v1/tasks/* must stay download-only (no state machine, no triggers)
