from __future__ import annotations

import os
from typing import Dict

from gateway.app.i18n import TRANSLATIONS as BASE_TRANSLATIONS

PRIMARY_UI_LANG = os.getenv("PRIMARY_UI_LANG", "zh")
SECONDARY_UI_LANG = os.getenv("SECONDARY_UI_LANG", "my")
ENABLE_SECONDARY_UI = os.getenv("ENABLE_SECONDARY_UI", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

I18N: Dict[str, Dict[str, str]] = {
    lang: dict(values) for lang, values in BASE_TRANSLATIONS.items()
}
I18N.setdefault("zh", {}).update(
    {
        "task_board": "任务看板",
        "task_count": "已加载 {n} 个任务。",
        "new_suitcase_task": "新建行李箱任务",
        "status_legend": "状态说明",
        "status_ready": "已就绪",
        "status_processing": "处理中",
        "status_pending": "排队中",
        "status_error": "失败",
        "download": "下载",
        "open": "打开",
        "json": "JSON",
        "pack": "剪辑包",
        "publish": "发布归档",
        "publish_now": "发布到归档",
        "published": "已发布",
        "not_published": "未发布",
        "publish_provider": "归档位置",
        "publish_key": "归档 Key",
        "publish_url": "下载链接",
        "refresh_link": "刷新下载链接",
    }
)
I18N.setdefault("my", {}).update(
    {
        "task_board": "တာဝန်ဘုတ်",
        "task_count": "တာဝန် {n} ခု တင်ပြီး။",
        "new_suitcase_task": "ခရီးဆောင်အိတ် တာဝန်အသစ်",
        "status_legend": "အခြေအနေဖော်ပြချက်",
        "status_ready": "အဆင်သင့်",
        "status_processing": "လုပ်ဆောင်နေသည်",
        "status_pending": "စောင့်ဆိုင်းနေသည်",
        "status_error": "မအောင်မြင်",
        "download": "ဒေါင်းလုဒ်",
        "open": "ဖွင့်",
        "json": "JSON",
        "pack": "ဖြတ်တည်းပုံး",
        "publish": "ထုတ်ပြန်/သိမ်းဆည်း",
        "publish_now": "သိမ်းဆည်းရန်",
        "published": "သိမ်းပြီး",
        "not_published": "မသိမ်းရသေး",
        "publish_provider": "သိမ်းရာနေရာ",
        "publish_key": "သိမ်းဆည်း Key",
        "publish_url": "ဒေါင်းလုဒ်လင့်",
        "refresh_link": "လင့်ကို ပြန်ယူ",
    }
)


def _t(lang: str, key: str, **kwargs) -> str:
    table = I18N.get(lang, {})
    s = table.get(key)
    if s is None and lang != "zh":
        s = I18N.get("zh", {}).get(key)
    if s is None and lang != "en":
        s = I18N.get("en", {}).get(key)
    if s is None:
        s = key
    try:
        return s.format(**kwargs)
    except Exception:
        return s


def t_primary(key: str, **kwargs) -> str:
    return _t(PRIMARY_UI_LANG, key, **kwargs)


def t_secondary(key: str, **kwargs) -> str:
    if not ENABLE_SECONDARY_UI:
        return ""
    return _t(SECONDARY_UI_LANG, key, **kwargs)


def ui_langs() -> dict[str, object]:
    return {
        "primary": PRIMARY_UI_LANG,
        "secondary": SECONDARY_UI_LANG,
        "secondary_enabled": ENABLE_SECONDARY_UI,
    }
