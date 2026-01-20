from fastapi.testclient import TestClient

from gateway.app.main import app


client = TestClient(app)


def test_tools_list_total():
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 18


def test_tools_search_ffmpeg():
    resp = client.get("/api/tools?q=ffmpeg")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any("ffmpeg" in item["tool_id"] for item in items)


def test_tools_get_redacts_secret():
    resp = client.get("/api/tools/google:veo")
    assert resp.status_code == 200
    data = resp.json()
    assert "secret_ref" not in (data.get("auth") or {})


def test_tools_get_missing():
    resp = client.get("/api/tools/does-not-exist")
    assert resp.status_code == 404
