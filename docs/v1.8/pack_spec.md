# v1.8 Pack Spec (capcut_v18)

## Purpose
Define the canonical ZIP contents and internal paths for v1.8 CapCut packs.

## ZIP root
All entries are stored under:

`deliver/packs/<task_id>/`

## Required entries
- `deliver/packs/<task_id>/raw/raw.mp4`
- `deliver/packs/<task_id>/audio/voice_my.<ext>`
- `deliver/packs/<task_id>/subs/my.srt`
- `deliver/packs/<task_id>/scenes/.keep`
- `deliver/packs/<task_id>/manifest.json`
- `deliver/packs/<task_id>/README.md`

## Manifest format (minimal)
```json
{
  "version": "1.8",
  "pack_type": "capcut_v18",
  "task_id": "<task_id>",
  "language": "my",
  "assets": {
    "raw_video": "raw/raw.mp4",
    "voice": "audio/voice_my.<ext>",
    "subtitle": "subs/my.srt",
    "scenes_dir": "scenes/"
  }
}
```

## Notes
- `voice_my.<ext>` uses the actual audio suffix from the source (`.wav` or `.mp3`).
- `.keep` is a placeholder to ensure `scenes/` exists in the ZIP.
- This spec is v1.8 only and must not alter v1.7 pack layout.
