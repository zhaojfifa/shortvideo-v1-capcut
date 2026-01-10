from fastapi.testclient import TestClient

from gateway.app.main import app


def test_mainline_smoke():
    client = TestClient(app)
    assert client.get("/tasks").status_code == 200
    assert client.get("/api/tasks?limit=1").status_code == 200
    assert client.get("/ui").status_code == 200
