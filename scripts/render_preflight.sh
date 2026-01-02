#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/var/data}"

echo "[preflight] ensure dirs under ${DATA_DIR}"
mkdir -p "${DATA_DIR}/.cache" "${DATA_DIR}/models" "${DATA_DIR}/tmp" "${DATA_DIR}/bin"

echo "[preflight] ffmpeg"
ffmpeg -version | head -n 2

echo "[preflight] edge-tts"
edge-tts --version

echo "[preflight] faster-whisper import"
python -c "from faster_whisper import WhisperModel; print('faster-whisper import ok')"

echo "[preflight] done"
