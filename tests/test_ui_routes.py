from pathlib import Path

def test_task_workbench_uses_api_triggers() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "gateway" / "app" / "templates" / "task_workbench.html"
    text = path.read_text(encoding="utf-8")

    # Must use /api/tasks/* triggers
    assert "/api/tasks/${taskId}/parse" in text
    assert "/api/tasks/${taskId}/subtitles" in text
    assert "/api/tasks/${taskId}/dub" in text
    assert "/api/tasks/${taskId}/pack" in text

    # Must not call v1 subtitles from Workbench
    assert "/v1/subtitles" not in text
