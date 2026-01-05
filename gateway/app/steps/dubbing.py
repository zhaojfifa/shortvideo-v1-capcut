from gateway.app.schemas import DubRequest
from gateway.app.services.steps_v1 import run_dub_step as run_dub_step_v1


async def run_dub_step(task):
    task_id = getattr(task, "id", None) or getattr(task, "task_id", None)
    if not task_id:
        raise ValueError("Missing task id for dub step")
    voice_id = getattr(task, "voice_id", None)
    force = bool(getattr(task, "force_dub", False) or getattr(task, "force", False))
    target_lang = (
        getattr(task, "target_lang", None)
        or getattr(task, "content_lang", None)
        or "my"
    )
    mm_text = getattr(task, "mm_text", None)
    if isinstance(mm_text, str):
        mm_text = mm_text.strip() or None
    req = DubRequest(
        task_id=task_id,
        voice_id=voice_id,
        target_lang=target_lang,
        force=force,
        mm_text=mm_text,
    )
    return await run_dub_step_v1(req)
