from collections import defaultdict

from gateway.app.main import app


def test_route_inventory():
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = tuple(sorted(route.methods))
            routes.append((route.path, methods, getattr(route, "name", "")))

    required = [
        ("GET", "/tasks"),
        ("GET", "/tasks/new"),
        ("GET", "/ui"),
        ("GET", "/api/tasks"),
        ("POST", "/api/tasks"),
        ("GET", "/api/tasks/{task_id}"),
        ("DELETE", "/api/tasks/{task_id}"),
        ("POST", "/api/tasks/{task_id}/subtitles"),
        ("POST", "/api/tasks/{task_id}/dub"),
        ("POST", "/api/tasks/{task_id}/scenes"),
        ("POST", "/api/tasks/{task_id}/pack"),
        ("POST", "/v1/parse"),
        ("POST", "/v1/subtitles"),
        ("POST", "/v1/pack"),
        ("GET", "/v1/tasks/{task_id}/status"),
    ]

    missing = []
    for method, path in required:
        found = any(path == r_path and method in r_methods for r_path, r_methods, _ in routes)
        if not found:
            missing.append(f"{method} {path}")

    print("Verified required routes:", ", ".join(f"{m} {p}" for m, p in required))
    assert not missing, f"Missing required routes: {', '.join(missing)}"

    seen = defaultdict(list)
    for path, methods, name in routes:
        seen[(path, methods)].append(name or "<unnamed>")

    duplicate_paths = [
        "/v1/tasks/{task_id}/raw",
        "/v1/tasks/{task_id}/subs_origin",
        "/v1/tasks/{task_id}/subs_mm",
        "/v1/tasks/{task_id}/mm_txt",
        "/v1/tasks/{task_id}/audio_mm",
        "/v1/tasks/{task_id}/pack",
        "/v1/tasks/{task_id}/scenes",
    ]

    duplicates = []
    for (path, methods), names in seen.items():
        if path in duplicate_paths and len(names) > 1:
            duplicates.append((path, methods, names))

    assert not duplicates, "Duplicate route handlers detected: " + "; ".join(
        f"{path} {methods} -> {names}" for path, methods, names in duplicates
    )
