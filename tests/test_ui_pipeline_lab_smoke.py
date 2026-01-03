from fastapi.testclient import TestClient

from gateway.app.main import app


def test_ui_pipeline_lab_smoke():
    client = TestClient(app)
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "/api/tasks" not in resp.text
    assert "/static/pipeline_lab.js" in resp.text
    assert "onclick=" not in resp.text
