from gateway.app.main import app

def test_no_duplicate_routes_for_pack_download():
    target_path = "/v1/tasks/{task_id}/pack"
    hits = []
    for r in app.routes:
        methods = getattr(r, "methods", None) or set()
        path = getattr(r, "path", None)
        if path == target_path and "GET" in methods:
            hits.append(r)
    assert len(hits) == 1, f"Expected exactly 1 GET {target_path}, got {len(hits)}"
