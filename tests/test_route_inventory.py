from __future__ import annotations

from collections import defaultdict

from gateway.app.main import app


def _collect_routes():
    routes = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if not path:
            continue
        for method in methods:
            routes.append((method, path))
    return routes


def _assert_route_exists(method: str, path: str, routes: list[tuple[str, str]]):
    if (method, path) not in routes:
        available = sorted({p for m, p in routes if m == method})
        raise AssertionError(
            f"Missing route {method} {path}. Available {method} routes: {available}"
        )


def test_route_inventory_and_duplicates():
    routes = _collect_routes()

    # Mainline task endpoints (must exist).
    _assert_route_exists("GET", "/tasks", routes)
    _assert_route_exists("GET", "/api/tasks", routes)
    _assert_route_exists("GET", "/api/tasks/{task_id}", routes)
    _assert_route_exists("POST", "/api/tasks/{task_id}/subtitles", routes)
    _assert_route_exists("POST", "/api/tasks/{task_id}/dub", routes)
    _assert_route_exists("POST", "/api/tasks/{task_id}/scenes", routes)

    # UI pipeline page.
    _assert_route_exists("GET", "/ui", routes)

    # V1 pipeline endpoints.
    _assert_route_exists("POST", "/v1/parse", routes)
    _assert_route_exists("POST", "/v1/subtitles", routes)
    _assert_route_exists("POST", "/v1/pack", routes)

    # Duplicate detection for v1 downloads.
    counts = defaultdict(int)
    for method, path in routes:
        if method == "GET" and path.startswith("/v1/tasks/"):
            counts[path] += 1

    duplicates = {path: count for path, count in counts.items() if count > 1}
    if duplicates:
        raise AssertionError(f"Duplicate /v1/tasks download routes: {duplicates}")

    # Explicitly guard known critical downloads.
    pack_path = "/v1/tasks/{task_id}/pack"
    scenes_path = "/v1/tasks/{task_id}/scenes"
    if counts.get(pack_path, 0) != 1:
        raise AssertionError(f"Expected exactly one GET {pack_path}, got {counts.get(pack_path, 0)}")
    if counts.get(scenes_path, 0) != 1:
        raise AssertionError(f"Expected exactly one GET {scenes_path}, got {counts.get(scenes_path, 0)}")
