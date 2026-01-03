from __future__ import annotations


def _count_routes(app, path: str, method: str | None = None) -> int:
    hits = 0
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method:
            methods = getattr(route, "methods", None) or set()
            if method.upper() not in methods:
                continue
        hits += 1
    return hits


def test_pack_route_unique_in_primary_app() -> None:
    from gateway.main import app as primary_app

    assert _count_routes(primary_app, "/api/tasks/{task_id}/parse", "POST") == 1
    assert _count_routes(primary_app, "/api/tasks/{task_id}/pack", "POST") == 1
    assert _count_routes(primary_app, "/v1/tasks/{task_id}/pack", "GET") == 1
    assert _count_routes(primary_app, "/v1/tasks/{task_id}/scenes", "GET") == 1
    assert _count_routes(primary_app, "/api/tasks/{task_id}/scenes", "POST") == 1
    assert _count_routes(primary_app, "/api/tasks/{task_id}/subtitles", "POST") == 1


def test_pack_route_unique_in_legacy_app() -> None:
    from gateway.app.main import app as legacy_app

    assert _count_routes(legacy_app, "/api/tasks/{task_id}/parse", "POST") == 1
    assert _count_routes(legacy_app, "/api/tasks/{task_id}/pack", "POST") == 1
    assert _count_routes(legacy_app, "/v1/tasks/{task_id}/pack", "GET") == 1
    assert _count_routes(legacy_app, "/v1/tasks/{task_id}/scenes", "GET") == 1
    assert _count_routes(legacy_app, "/api/tasks/{task_id}/scenes", "POST") == 1
    assert _count_routes(legacy_app, "/api/tasks/{task_id}/subtitles", "POST") == 1


def test_v17_pack_route_exists() -> None:
    from gateway.app.main import app as legacy_app

    assert _count_routes(legacy_app, "/v1.7/pack/youcut") == 1


def test_services_do_not_import_adapters() -> None:
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "gateway" / "app" / "services",
        root / "gateway" / "app" / "steps",
        root / "gateway" / "app" / "routers",
    ]
    pattern = re.compile(r"gateway\\.app\\.adapters")

    for base in targets:
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert not pattern.search(text), f"Adapter import found in {path}"
