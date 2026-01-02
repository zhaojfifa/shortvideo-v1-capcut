# v1.8 Scenes Package Spec

## Purpose
Define the ZIP layout and manifest for scene slicing output (separate from pack.zip).

## ZIP layout
```
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
  "source_subtitles": "mm|origin",
  "scenes": [
    {
      "scene_id": "scene_001",
      "start": 0.0,
      "end": 4.2,
      "duration": 4.2,
      "assets": {
        "video": "scenes/scene_001/video.mp4",
        "audio": "scenes/scene_001/audio.wav",
        "subs": "scenes/scene_001/subs.srt",
        "scene_json": "scenes/scene_001/scene.json"
      },
      "subtitle_preview": "first subtitle line"
    }
  ]
}
```

## Notes
- `README.md` includes a human-readable table for ops.
- MSC per scene: `video.mp4`, `audio.wav`, `subs.srt`, `scene.json`.
- Scenes package is uploaded to `deliver/scenes/<task_id>/scenes.zip`.
