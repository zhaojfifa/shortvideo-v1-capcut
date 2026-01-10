from fastapi.testclient import TestClient

from gateway.app.main import app


def test_root_route_ok() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json().get("ok") is True
