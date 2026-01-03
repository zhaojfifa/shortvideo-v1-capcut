from __future__ import annotations

from pathlib import Path


def test_task_workbench_does_not_call_v1_subtitles() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "gateway" / "app" / "templates" / "task_workbench.html"
    text = path.read_text(encoding="utf-8")
    assert "/v1/subtitles" not in text


def test_pipeline_lab_uses_v1_subtitles_only() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "gateway" / "app" / "templates" / "pipeline_lab.html",
        root / "gateway" / "app" / "static" / "ui.html",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "/v1/subtitles" in text
        assert "/api/tasks/" not in text
