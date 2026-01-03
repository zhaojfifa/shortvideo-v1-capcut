from fastapi.testclient import TestClient

from gateway.app.main import app


def test_v1_actions_routes_exist():
    client = TestClient(app)
    paths = ["/v1/parse", "/v1/subtitles", "/v1/dub", "/v1/pack"]
    for path in paths:
        resp = client.post(path, json={})
        assert resp.status_code != 404, f"{path} is not registered"
