import importlib.util
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.app.main import app


def test_v17_pack_youcut_tts_generates_wav(tmp_path: Path, monkeypatch):
    if importlib.util.find_spec("edge_tts") is None:
        pytest.skip("edge-tts not available")

    monkeypatch.setenv("V17_PACKS_DIR", str(tmp_path / "deliver" / "packs"))

    client = TestClient(app)
    r = client.post(
        "/v1.7/pack/youcut",
        json={
            "task_id": "demo_v17_tts",
            "zip": False,
            "upload": False,
            "placeholders": True,
            "tts": True,
            "voice": "my-MM-NilarNeural",
            "rate": "+0%",
            "pitch": "+0Hz",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    pack_root = Path(data["pack_root"])
    wav_path = pack_root / "audio" / "voice_my.wav"
    assert wav_path.exists()
    assert wav_path.stat().st_size > 0
