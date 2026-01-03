from __future__ import annotations

from pathlib import Path


def test_task_workbench_does_not_call_v1_subtitles() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "gateway" / "app" / "templates" / "task_workbench.html"
    text = path.read_text(encoding="utf-8")
    assert "/v1/subtitles" not in text


def test_pipeline_lab_uses_v1_subtitles_only() -> None:
    root = Path(__file__).resolve().parents[1]
    template_path = root / "gateway" / "app" / "templates" / "pipeline_lab.html"
    static_path = root / "gateway" / "app" / "static" / "ui.html"
    script_path = root / "gateway" / "app" / "static" / "pipeline_lab.js"

    template_text = template_path.read_text(encoding="utf-8")
    static_text = static_path.read_text(encoding="utf-8")
    script_text = script_path.read_text(encoding="utf-8")

    assert "/api/tasks/" not in template_text
    assert "/api/tasks/" not in static_text
    assert "/api/tasks/" not in script_text
    assert "/v1/subtitles" in script_text
    assert "/v1/parse" in script_text
    assert "/v1/pack" in script_text
    assert "/v1/tasks/" in script_text
