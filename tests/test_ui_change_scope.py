from __future__ import annotations

from pathlib import Path


def test_ui_scope_guardrails() -> None:
    root = Path(__file__).resolve().parents[1]
    allowed = {
        root / "gateway" / "app" / "templates" / "pipeline_lab.html",
        root / "gateway" / "app" / "static" / "ui.html",
        root / "gateway" / "app" / "static" / "pipeline_lab.js",
    }

    markers = [
        "/v1/parse",
        "/v1/subtitles",
        "/v1/dub",
        "/v1/pack",
    ]

    offenders = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".html", ".js"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in markers):
            if path not in allowed:
                offenders.append(str(path.relative_to(root)))

    assert not offenders, f"UI pipeline logic found outside allowed files: {offenders}"


def test_ui_files_do_not_call_task_api() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "gateway" / "app" / "templates" / "pipeline_lab.html",
        root / "gateway" / "app" / "static" / "ui.html",
        root / "gateway" / "app" / "static" / "pipeline_lab.js",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "/api/tasks" not in text, f"/api/tasks referenced in {path}"
        assert "setInterval(" not in text, f"Polling detected in {path}"
        assert "setTimeout(" not in text, f"Timer detected in {path}"
