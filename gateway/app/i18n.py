from __future__ import annotations

from gateway.app.config import get_settings


TRANSLATIONS = {
    "zh": {
        "task_board": "任务看板",
        "task_workbench": "任务工作台",
        "new_suitcase_task": "新建行李箱任务",
        "id": "ID",
        "platform": "平台",
        "source": "来源",
        "title": "标题",
        "category": "分类",
        "lang": "语言",
        "status": "状态",
        "created": "创建时间",
        "pack": "剪辑包",
        "detail": "详情",
        "downloads": "素材下载",
        "download": "下载",
        "open": "打开",
        "json": "JSON",
        "processing": "处理中",
        "ready": "已就绪",
        "error": "失败",
        "pending": "排队中",
        "re_run_subtitles": "重跑字幕",
        "re_run_dub": "重跑配音",
        "re_run_pack": "重跑打包",
        "log": "日志",
        "step2": "步骤二",
        "step3": "步骤三",
        "step4": "步骤四",
    },
    "my": {
        "task_board": "အလုပ်စာရင်းဘုတ်",
        "task_workbench": "အလုပ်လုပ်ခန်း",
        "new_suitcase_task": "ခရီးဆောင်သေတ္တာ任务အသစ်",
        "id": "အိုင်ဒီ",
        "platform": "ပလက်ဖောင်း",
        "source": "အရင်းအမြစ်",
        "title": "ခေါင်းစဉ်",
        "category": "အမျိုးအစား",
        "lang": "ဘာသာစကား",
        "status": "အခြေအနေ",
        "created": "ဖန်တီးချိန်",
        "pack": "ကပ်ကတ်ပက်",
        "detail": "အသေးစိတ်",
        "downloads": "ဒေါင်းလုဒ်ပစ္စည်းများ",
        "download": "ဒေါင်းလုဒ်",
        "open": "ဖွင့်ရန်",
        "json": "JSON",
        "processing": "လုပ်ဆောင်နေဆဲ",
        "ready": "ပြီးပြည့်စုံ",
        "error": "အမှား",
        "pending": "စောင့်ဆိုင်းနေ",
        "re_run_subtitles": "စာတန်းထိုးပြန်လုပ်",
        "re_run_dub": "အသံပြန်လုပ်",
        "re_run_pack": "ပက်ပြန်လုပ်",
        "log": "မှတ်တမ်း",
        "step2": "အဆင့်၂",
        "step3": "အဆင့်၃",
        "step4": "အဆင့်၄",
    },
}


def t(key: str, lang: str, fallback_lang: str = "en") -> str:
    if lang in TRANSLATIONS and key in TRANSLATIONS[lang]:
        return TRANSLATIONS[lang][key]
    if fallback_lang in TRANSLATIONS and key in TRANSLATIONS[fallback_lang]:
        return TRANSLATIONS[fallback_lang][key]
    return key


def t_primary(key: str) -> str:
    settings = get_settings()
    return t(key, settings.ui_primary_lang)


def t_secondary(key: str) -> str:
    settings = get_settings()
    return t(key, settings.ui_secondary_lang, fallback_lang=settings.ui_primary_lang)


def t_bi(key: str) -> dict[str, str]:
    return {
        "primary": t_primary(key),
        "secondary": t_secondary(key),
    }
