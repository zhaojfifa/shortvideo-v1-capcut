#!/usr/bin/env bash
set -euo pipefail

echo "[build] python=$(python --version)"
echo "[build] pip=$(python -m pip --version)"

python -m pip install -U pip
python -m pip install -r requirements.txt

# ---- install static ffmpeg (no apt-get) ----
mkdir -p .render/bin /tmp/ffmpeg

# A widely used static build source (Linux x86_64)
FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"

echo "[build] downloading ffmpeg static..."
curl -L "$FFMPEG_URL" -o /tmp/ffmpeg/ffmpeg.tar.xz

echo "[build] extracting ffmpeg..."
tar -xJf /tmp/ffmpeg/ffmpeg.tar.xz -C /tmp/ffmpeg

# archive contains a single directory
FFDIR="$(find /tmp/ffmpeg -maxdepth 1 -type d -name 'ffmpeg-*' | head -n 1)"
test -n "$FFDIR"

cp -f "$FFDIR/ffmpeg" "$FFDIR/ffprobe" .render/bin/
chmod +x .render/bin/ffmpeg .render/bin/ffprobe

echo "[build] ffmpeg installed at .render/bin"
