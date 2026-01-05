from __future__ import annotations

import os
from typing import Dict

from markupsafe import Markup, escape

from gateway.app.i18n import TRANSLATIONS as BASE_TRANSLATIONS

PRIMARY_UI_LANG = os.getenv("PRIMARY_UI_LANG", "zh")
SECONDARY_UI_LANG = os.getenv("SECONDARY_UI_LANG", "my")
UI_BILINGUAL = os.getenv("UI_BILINGUAL", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ENABLE_SECONDARY_UI = os.getenv("ENABLE_SECONDARY_UI", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SHOW_BILINGUAL = ENABLE_SECONDARY_UI and UI_BILINGUAL

I18N: Dict[str, Dict[str, str]] = {
    lang: dict(values) for lang, values in BASE_TRANSLATIONS.items()
}
I18N.setdefault("zh", {}).update(
    {
        "task_board": "任务看板",
        "task_count": "任务数 {n} 个",
        "new_suitcase_task": "新建任务",
        "new_task": "新建任务",
        "back_to_task_board": "返回任务看板",
        "status_legend": "状态说明",
        "status_ready": "已就绪",
        "status_processing": "处理中",
        "status_pending": "未开始",
        "status_error": "失败",
        "status_unknown": "未知",
        "download": "下载",
        "open": "打开",
        "json": "JSON",
        "pack": "剪辑包",
        "publish": "发布",
        "publish_now": "立即发布",
        "published": "已发布",
        "not_published": "未发布",
        "publish_provider": "发布引擎",
        "publish_key": "发布 Key",
        "publish_url": "发布链接",
        "refresh_link": "刷新链接",
        "refresh": "刷新",
        "deliverables": "交付物",
        "steps": "流程",
        "publish_info": "发布信息",
        "provider": "引擎",
        "status": "状态",
        "ready": "已就绪",
        "not_ready": "未就绪",
        "parsed": "已解析",
        "not_parsed": "未解析",
        "queued": "排队中",
        "running": "处理中",
        "error": "失败",
        "publish_key_label": "发布 Key",
        "publishing_text": "发布文案",
        "publish_url_label": "发布链接",
        "publish_now_label": "立即发布",
        "copy": "复制",
        "run_parse": "运行解析",
        "gen_subtitles": "生成字幕",
        "gen_dub": "生成配音",
        "build_pack": "生成剪辑包",
        "build_scenes": "生成场景包",
        "source_url": "来源链接",
        "platform": "平台",
        "account": "账号",
        "video_type": "视频类型",
        "style_preset": "风格模板",
        "title_optional": "标题（可选）",
        "note_hint": "备注",
        "create_and_run": "创建并运行",
        "created_task": "已创建任务",
        "submitting": "提交中...",
        "source_url_required": "来源链接不能为空",
        "request_failed": "请求失败",
        "error_prefix": "错误",
    }
)
I18N.setdefault("my", {}).update(
    {
        "task_board": "အလုပ်စာရင်း",
        "task_count": "အလုပ် {n} ခု",
        "new_suitcase_task": "အလုပ်အသစ်",
        "new_task": "အလုပ်အသစ်",
        "back_to_task_board": "အလုပ်စာရင်းသို့ ပြန်သွားရန်",
        "status_legend": "အခြေအနေရှင်းလင်းချက်",
        "status_ready": "အဆင်သင့်",
        "status_processing": "လုပ်ဆောင်နေသည်",
        "status_pending": "မစရသေး",
        "status_error": "မအောင်မြင်",
        "status_unknown": "မသိ",
        "download": "ဒေါင်းလုပ်",
        "open": "ဖွင့်",
        "json": "JSON",
        "pack": "ဗီဒီယိုပက်ကেজ်",
        "publish": "ထုတ်ဝေ",
        "publish_now": "ချက်ချင်းထုတ်ဝေ",
        "published": "ထုတ်ဝေပြီး",
        "not_published": "မထုတ်ဝေသေး",
        "publish_provider": "ပံ့ပိုးသူ",
        "publish_key": "ထုတ်ဝေ Key",
        "publish_url": "ထုတ်ဝေလင့်ခ်",
        "refresh_link": "လင့်ခ်ပြန်လည်ယူ",
        "refresh": "ပြန်လည်တင်",
        "deliverables": "ပေးပို့ရန်ပစ္စည်းများ",
        "steps": "လုပ်ငန်းစဉ်",
        "publish_info": "ထုတ်ဝေမှုအချက်အလက်",
        "provider": "ပံ့ပိုးသူ",
        "status": "အခြေအနေ",
        "ready": "အဆင်သင့်",
        "not_ready": "မအဆင်သင့်",
        "parsed": "ခွဲပြီး",
        "not_parsed": "မခွဲသေး",
        "queued": "တန်းစီထားသည်",
        "running": "လုပ်ဆောင်နေသည်",
        "error": "မအောင်မြင်",
        "publish_key_label": "ထုတ်ဝေ Key",
        "publishing_text": "ထုတ်ဝေစာသား",
        "publish_url_label": "ထုတ်ဝေလင့်ခ်",
        "publish_now_label": "ယခုပဲထုတ်ဝေ",
        "copy": "ကူးယူ",
        "run_parse": "ခွဲရန်",
        "gen_subtitles": "စာတန်းထိုးထုတ်ရန်",
        "gen_dub": "အသံထုတ်ရန်",
        "build_pack": "ပက်ကက် ထုတ်ရန်",
        "build_scenes": "Scene များ ထုတ်ရန်",
        "source_url": "အရင်းအမြစ်လင့်ခ်",
        "platform": "ပလက်ဖောင်း",
        "account": "အကောင့်",
        "video_type": "ဗီဒီယိုအမျိုးအစား",
        "style_preset": "စတိုင်ပုံစံ",
        "title_optional": "ခေါင်းစဉ် (ရွေးချယ်နိုင်)",
        "note_hint": "မှတ်ချက်",
        "create_and_run": "ဖန်တီးပြီး အလုပ်လုပ်မည်",
        "created_task": "အလုပ် ဖန်တီးပြီး",
        "submitting": "ပို့နေသည်...",
        "source_url_required": "အရင်းအမြစ်လင့်ခ် လိုအပ်သည်",
        "request_failed": "တောင်းဆိုမှု မအောင်မြင်",
        "error_prefix": "အမှား",
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
    if not SHOW_BILINGUAL:
        return ""
    return _t(SECONDARY_UI_LANG, key, **kwargs)


def bi(zh: str, mm: str) -> Markup:
    if not SHOW_BILINGUAL or not mm:
        return Markup(f'<span class="bi-zh">{escape(zh)}</span>')
    return Markup(
        f'<span class="bi-zh">{escape(zh)}</span>'
        f'<span class="bi-mm">{escape(mm)}</span>'
    )


def ui_langs() -> dict[str, object]:
    return {
        "primary": PRIMARY_UI_LANG,
        "secondary": SECONDARY_UI_LANG,
        "secondary_enabled": SHOW_BILINGUAL,
        "bilingual": SHOW_BILINGUAL,
    }
