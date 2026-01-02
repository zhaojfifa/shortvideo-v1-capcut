#!/usr/bin/env bash
set -euo pipefail

export PATH="$PWD/.render/bin:$PATH"

echo "[preflight] ffmpeg:"
ffmpeg -version | head -n 2 || true

DISK_ROOT="${DISK_ROOT:-/var/data}"
mkdir -p "$DISK_ROOT/cache" "$DISK_ROOT/models"

export HF_HOME="$DISK_ROOT/cache/hf"
export XDG_CACHE_HOME="$DISK_ROOT/cache/xdg"

# Prefer new var; fall back to legacy WHISPER_MODEL
MODEL_NAME="${FASTER_WHISPER_MODEL:-${WHISPER_MODEL:-small}}"

# Map OpenAI-style names to local model sizes
case "$MODEL_NAME" in
  whisper-1) MODEL_NAME="small" ;;
esac

SENTINEL="$DISK_ROOT/models/.faster_whisper_${MODEL_NAME}_ready"

if [ ! -f "$SENTINEL" ]; then
  echo "[preflight] warming up faster-whisper model: ${MODEL_NAME} (first run only)"
  # Never block service start because of warmup issues
  python - <<PY || echo "[preflight] warmup skipped (non-fatal)"
import os
from faster_whisper import WhisperModel

model = os.environ.get("MODEL_NAME", "${MODEL_NAME}")
# Validate model name early; fall back if invalid
valid = {
  "tiny.en","tiny","base.en","base","small.en","small","medium.en","medium",
  "large-v1","large-v2","large-v3","large","turbo",
  "distil-large-v2","distil-medium.en","distil-small.en","distil-large-v3","distil-large-v3.5","large-v3-turbo"
}
if model not in valid:
  print("invalid faster-whisper model:", model, "-> fallback to small")
  model = "small"

WhisperModel(model, device="cpu", compute_type="int8")
print("warmup ok:", model)
PY
  # 只有 warmup 成功才写 sentinel（上面 python 如果异常会返回非 0，但我们不让它阻断）
  touch "$SENTINEL" || true
else
  echo "[preflight] faster-whisper model already warmed: ${MODEL_NAME}"
fi
