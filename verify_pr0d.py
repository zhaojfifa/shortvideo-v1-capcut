import sys
import os
import json
import asyncio  # <--- 必须引入这个
sys.path.append(os.getcwd())

from gateway.app.config import get_storage_service
from gateway.app.utils.keys import KeyBuilder

# === 关键修改：把验证函数变成 async ===
async def verify_ssot_loop():
    print(">>> 开始验证 PR-0D (SSOT 闭环)...")
    
    tenant = "verify"
    project = "pr0d"
    task_id = "ssot_test_01"
    
    storage = get_storage_service()
    
    # 1. 模拟一个 subtitles.json (像是用户编辑过的)
    sub_key = KeyBuilder.build(tenant, project, task_id, "artifacts/subtitles.json")
    mock_data = {
        "segments": [
              {
                "start": 0.0, 
                "end": 1.0, 
                "text": "Hello World", 
                "target": "Hello World (Translated)"  # <--- 必须加这个！
            },
            {
                "start": 1.0, 
                "end": 2.0, 
                "text": "Test", 
                "target": "Test Audio"                # <--- 必须加这个！
            }
        ]
    }
    
    print(f"1. 上传模拟字幕到: {sub_key}")
    with open("temp_sub.json", "w") as f:
        json.dump(mock_data, f)
    storage.upload_file("temp_sub.json", sub_key)
    
    # 2. 模拟运行 Dubbing Step
    try:
        from gateway.app.steps.dubbing import run_dub_step
        from gateway.app.models import Task
        
        # 构造一个假 Task 对象
        mock_task = Task(id=task_id, tenant_id=tenant, project_id=project, target_lang="en")
        
        print("2. 运行配音步骤 (应读取 JSON)...")
        
        try:
            # === 关键修改：加上 await ===
            await run_dub_step(mock_task) 
            print("✅ 配音步骤执行完毕")
        except Exception as e:
            print(f"⚠️ 运行报错: {e}")
            import traceback
            traceback.print_exc()

        # 3. 检查是否生成了 voice manifest
        manifest_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/manifest.json")
        if storage.exists(manifest_key):
            print("✅ Voice Manifest 已生成 (闭环成功)")
        else:
            print("❌ Voice Manifest 未生成")
            
    except ImportError:
        print("❌ 无法导入 dubbing step，请检查文件名")
    finally:
        if os.path.exists("temp_sub.json"): os.remove("temp_sub.json")

if __name__ == "__main__":
    # === 关键修改：使用 asyncio.run 启动 ===
    asyncio.run(verify_ssot_loop())