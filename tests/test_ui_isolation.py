from pathlib import Path


def test_ui_isolation():
    ui_path = Path("gateway/app/static/ui.html")
    content = ui_path.read_text(encoding="utf-8")
    assert "/api/tasks" not in content

    forbidden = ["\u2018", "\u2019", "\u201C", "\u201D", "\u2014"]
    found = [ch for ch in forbidden if ch in content]
    assert not found, f"Non-ASCII punctuation found in /ui HTML: {found}"
