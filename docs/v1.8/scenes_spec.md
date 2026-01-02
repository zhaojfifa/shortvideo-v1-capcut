# v1.8 Scenes Package Spec

## Purpose
Define the ZIP layout and manifest for scene slicing output (separate from pack.zip).

## ZIP layout
```
deliver/scenes/<task_id>/
  README.md
  scenes_manifest.json
  scenes/
    scene_001/
      video.mp4
      audio.wav
      subs.srt
      scene.json
```

## Manifest fields
`scenes_manifest.json` (minimal):
```json
{
  "version": "1.8",
  "task_id": "<task_id>",
  "language": "mm|origin",
  "created_at": "2026-01-02T10:00:00Z",
  "source": {
    "raw_video": "deliver/packs/<task_id>/raw/raw.mp4",
    "subs": "deliver/packs/<task_id>/subs/mm.srt"
  },
  "scenes": [
    {
      "scene_id": "scene_001",
      "start": 0.0,
      "end": 4.2,
      "duration": 4.2,
      "role": "unknown",
      "dir": "scenes/scene_001"
    }
  ]
}
```

## Notes
- `README.md` includes a human-readable table for ops.
- MSC per scene: `video.mp4`, `audio.wav`, `subs.srt`, `scene.json`.
- Scenes package is uploaded to `deliver/scenes/<task_id>/scenes.zip`.
