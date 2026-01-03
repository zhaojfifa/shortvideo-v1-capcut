from fastapi.testclient import TestClient
from gateway.app.main import app

def test_healthz_ok():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200

def test_v1_parse_route_registered_not_404():
    c = TestClient(app)
    r = c.post("/v1/parse", json={"task_id": "demo_v1", "link": "https://example.com"})
    assert r.status_code != 404
