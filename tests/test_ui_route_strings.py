from __future__ import annotations

from pathlib import Path


def test_task_workbench_uses_api_triggers() -> None:
    path = Path(__file__).resolve().parents[1] / "gateway" / "app" / "templates" / "task_workbench.html"
    text = path.read_text(encoding="utf-8")

    assert "/api/tasks/${taskId}/parse" in text
    assert "/api/tasks/${taskId}/subtitles" in text
    assert "/api/tasks/${taskId}/dub" in text
    assert "/api/tasks/${taskId}/pack" in text
    assert "/api/tasks/${taskId}/scenes" in text

    assert "/v1/parse" not in text
    assert "/v1/subtitles" not in text
    assert "/v1/dub" not in text
    assert "/v1/pack" not in text


def test_pipeline_lab_uses_v1_triggers() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "gateway" / "app" / "templates" / "pipeline_lab.html",
        root / "gateway" / "app" / "static" / "ui.html",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "/v1/parse" in text
        assert "/v1/subtitles" in text
        assert "/v1/dub" in text
        assert "/v1/pack" in text
        assert "/api/tasks/" not in text
