#!/usr/bin/env bash
set -euo pipefail

echo "[build] python:"
python --version

echo "[build] install ffmpeg"
apt-get update -y
apt-get install -y ffmpeg

echo "[build] pip install"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "[build] done"
