#!/usr/bin/env bash
set -euo pipefail

# 1) PATH: make bundled ffmpeg available
export PATH="$PWD/.render/bin:$PATH"

echo "[preflight] ffmpeg:"
ffmpeg -version | head -n 2 || true

# 2) persistent disk cache (mount path example: /var/data)
DISK_ROOT="${DISK_ROOT:-/var/data}"
mkdir -p "$DISK_ROOT/cache" "$DISK_ROOT/models"

# HuggingFace cache -> persistent disk
export HF_HOME="$DISK_ROOT/cache/hf"
export XDG_CACHE_HOME="$DISK_ROOT/cache/xdg"

# 3) optional: warm up faster-whisper model once
MODEL_NAME="${WHISPER_MODEL:-small}"
SENTINEL="$DISK_ROOT/models/.whisper_${MODEL_NAME}_ready"

if [ ! -f "$SENTINEL" ]; then
  echo "[preflight] warming up faster-whisper model: ${MODEL_NAME} (first run only)"
  python - <<'PY'
import os
from faster_whisper import WhisperModel

model = os.environ.get("WHISPER_MODEL", "small")
# CPU baseline; int8 is usually the best tradeoff on Render CPU
WhisperModel(model, device="cpu", compute_type="int8")
print("warmup ok:", model)
PY
  touch "$SENTINEL"
else
  echo "[preflight] whisper model already warmed: ${MODEL_NAME}"
fi
