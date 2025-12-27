import os
from pathlib import Path

from gateway.app.services.artifact_storage import upload_task_artifact, object_exists, get_object_bytes
from gateway.app.utils.keys import KeyBuilder

def main():
    # 构造一个最小 task dict（按你们 KeyBuilder 的字段命名调整）
    task = {
        "task_id": "smoke123456",
        "tenant_id": "default",
        "project_id": "default",
    }

    p = Path("tmp_smoke.txt")
    p.write_text("hello storage", encoding="utf-8")

    # 你们当前 upload_task_artifact 的签名不确定——用一次真实调用来确认
    key = upload_task_artifact(task, p, "artifacts/smoke.txt", task_id=task["task_id"])
    print("uploaded key:", key)

    assert object_exists(key), f"object_exists failed for key={key}"

    data = get_object_bytes(key)
    assert data is not None and b"hello storage" in data, "get_object_bytes failed"

    # 再对照 KeyBuilder.build 的期望
    expected = KeyBuilder.build(task["tenant_id"], task["project_id"], task["task_id"], "artifacts/smoke.txt")
    print("expected key:", expected)

    print("OK")

if __name__ == "__main__":
    main()
