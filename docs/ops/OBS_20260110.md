# OBS Baseline ¡ª 2026-01-10 (v1.8)

## Evidence
Two tasks completed E2E in Render production:
- parse ¡ú subtitles (faster-whisper + Gemini) ¡ú dub (edge-tts) ¡ú pack succeeded.
- Long video succeeded via looped segmentation translation.

## Findings (no pipeline changes)
1) Deployment/startup OK: routes registered, ffmpeg present, service live.
2) Subtitles stable: WAV extract OK, ASR language detected, Gemini chunked translations return 200/STOP, artifacts uploaded.
3) Dub + pack stable: TTS completes, pack timing recorded.

## Low-risk ops improvements (PR-OBS-03 scope)
- Log the computed ASR timeout value at stage SUB2_ASR_TIMEOUT (asr_timeout_sec=...).
- Deduplicate logger handlers to avoid repeated log blocks (guard handlers + propagate=False).
- Reduce constant TASK_REPO_BACKEND log noise (startup-only or DEBUG).
- (Optional) Make GET/HEAD / return 200 to reduce Render 404 noise.
