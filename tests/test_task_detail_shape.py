from fastapi.testclient import TestClient

from gateway.app.main import app


def test_task_detail_shape():
    client = TestClient(app)
    create_resp = client.post("/api/tasks", json={"source_url": "https://example.com/video"})
    assert create_resp.status_code == 200
    task_id = create_resp.json().get("task_id")
    assert task_id

    detail_resp = client.get(f"/api/tasks/{task_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    print("Task detail keys:", sorted(data.keys()))

    for key in (
        "status",
        "last_step",
        "subtitles_status",
        "dub_status",
        "scenes_status",
        "pack_status",
        "subtitles_error",
        "dub_error",
        "scenes_error",
        "pack_error",
        "raw_path",
        "origin_srt_path",
        "mm_srt_path",
        "mm_txt_path",
        "mm_audio_path",
        "pack_path",
        "scenes_path",
        "updated_at",
        "stale",
        "stale_reason",
        "stale_for_seconds",
    ):
        assert key in data
