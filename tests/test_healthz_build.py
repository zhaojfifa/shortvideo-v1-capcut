from fastapi.testclient import TestClient

from gateway.app.main import app


def test_healthz_build_exists():
    client = TestClient(app)
    r = client.get("/healthz/build")
    assert r.status_code in (200, 503)
    data = r.json()
    assert "git_sha" in data
    assert "has_pack_v17_youcut" in data
    assert data["service"] == "shortvideo-v1-capcut"
    assert "edge_tts" in data
    assert "r2_enabled" in data
    assert data["pack_v17_status"] == "frozen"


def test_healthz_exists():
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
