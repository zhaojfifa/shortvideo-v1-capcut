from __future__ import annotations

import os
from typing import Callable, Dict

UI_PRIMARY_LANG = os.getenv("UI_PRIMARY_LANG", "zh")
UI_SECONDARY_LANG = os.getenv("UI_SECONDARY_LANG", "my")

I18N: Dict[str, Dict[str, str]] = {
    "zh": {
        "task_board": "任务看板",
        "new_suitcase_task": "新建拉杆箱任务",
        "platform": "平台",
        "source": "来源",
        "title": "标题",
        "category": "品类",
        "lang": "语言",
        "status": "状态",
        "created": "创建时间",
        "pack": "剪辑包",
        "detail": "详情",
        "download": "下载",
        "open": "打开",
        "json": "JSON",
        "ready": "就绪",
        "processing": "处理中",
        "error": "错误",
        "no_tasks": "暂无任务",
    },
    "my": {
        "task_board": "Task Board",
        "new_suitcase_task": "New Suitcase Task",
        "platform": "Platform",
        "source": "Source",
        "title": "Title",
        "category": "Category",
        "lang": "Lang",
        "status": "Status",
        "created": "Created",
        "pack": "Pack",
        "detail": "Detail",
        "download": "Download",
        "open": "Open",
        "json": "JSON",
        "ready": "ready",
        "processing": "processing",
        "error": "error",
        "no_tasks": "No tasks",
    },
}


def _t(lang: str) -> Callable[[str], str]:
    table = I18N.get(lang, {})

    def tr(key: str) -> str:
        return table.get(key, key)

    return tr


def get_template_globals() -> Dict[str, object]:
    primary = UI_PRIMARY_LANG or "zh"
    secondary = UI_SECONDARY_LANG or "my"
    return {
        "t_primary": _t(primary),
        "t_secondary": _t(secondary),
        "ui_primary_lang": primary,
        "ui_secondary_lang": secondary,
    }
