from __future__ import annotations

import re
from pathlib import Path


def test_task_ui_templates_do_not_fetch_v1() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "gateway" / "app" / "templates" / "tasks.html",
        root / "gateway" / "app" / "templates" / "tasks_board.html",
        root / "gateway" / "app" / "templates" / "task_workbench.html",
    ]
    pattern = re.compile(r"fetch\(\s*['\"]/v1/")
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert not pattern.search(text), f"/v1 fetch found in {path}"
