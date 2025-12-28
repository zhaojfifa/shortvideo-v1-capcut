import os
from pathlib import Path

from fastapi.testclient import TestClient

from gateway.app.main import app


def test_v17_pack_youcut_creates_zip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("V17_PACKS_DIR", str(tmp_path / "deliver" / "packs"))

    client = TestClient(app)
    r = client.post("/v1.7/pack/youcut", json={"task_id": "demo_v17_001", "zip": True, "placeholders": True})
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["task_id"] == "demo_v17_001"
    assert data["pack_type"] == "youcut_ready"
    assert "pack_root" in data and "zip_path" in data

    pack_root = Path(data["pack_root"])
    zip_path = Path(data["zip_path"])

    assert pack_root.exists()
    assert (pack_root / "manifest.json").exists()
    assert (pack_root / "README.md").exists()
    assert (pack_root / "raw" / "raw.mp4").exists()
    assert (pack_root / "audio" / "voice_my.wav").exists()
    assert (pack_root / "subs" / "my.srt").exists()
    assert (pack_root / "scenes" / "scene_001.mp4").exists()

    assert zip_path.exists()
    assert zip_path.suffix == ".zip"
