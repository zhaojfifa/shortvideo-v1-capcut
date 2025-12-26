import sys
import os
import json
import asyncio
sys.path.append(os.getcwd())

from gateway.app.config import get_storage_service
from gateway.app.utils.keys import KeyBuilder

async def verify_brief_step():
    print(">>> 开始验证 v1.65 PR-1 (Brief 生成)...")
    
    tenant = "verify"
    project = "pr1"
    task_id = "brief_test_01"
    
    storage = get_storage_service()
    
    # 1. 准备前置数据 (模拟 subtitles.json)
    # Brief 生成依赖字幕内容，所以我们需要先伪造一个字幕文件
    sub_key = KeyBuilder.build(tenant, project, task_id, "artifacts/subtitles.json")
    mock_subs = {
        "segments": [
            {"text": "Hey guys! Look at this amazing suitcase.", "start": 0, "end": 2},
            {"text": "It is unbreakable and very cheap.", "start": 2, "end": 4},
            {"text": "Click the link below to buy now!", "start": 4, "end": 6}
        ]
    }
    # ✅ 先创建本地文件
    with open("temp_subs.json", "w") as f:
        json.dump(mock_subs, f)

    # ✅ 再上传
    storage.upload_file("temp_subs.json", sub_key)
    print(f"1. 模拟字幕已上传: {sub_key}")

    # 2. 运行 Brief Step
    try:
        from gateway.app.steps.brief import run_brief_step
        from gateway.app.models import Task
        
        # 构造 Task 对象
        mock_task = Task(id=task_id, tenant_id=tenant, project_id=project, target_lang="my")
        
        print("2. 正在执行 Brief 生成步骤 (调用 Gemini)...")
        # 注意：这一步需要你的 .env 里配置了有效的 GEMINI_API_KEY
        await run_brief_step(mock_task)
        print("✅ 步骤执行完成")
        
        # 3. 验证产物 brief.json
        brief_key = KeyBuilder.build(tenant, project, task_id, "artifacts/brief.json")
        if storage.exists(brief_key):
            print(f"✅ Brief 文件已生成: {brief_key}")
            
            # 下载来看看内容对不对
            storage.download_file(brief_key, "temp_brief_result.json")
            with open("temp_brief_result.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                print("\n--- Brief Content Preview ---")
                print(f"Summary: {data.get('summary')}")
                print(f"Selling Points: {data.get('selling_points')}")
                print("-----------------------------")
        else:
            print("❌ Brief 文件未生成！")

    except ImportError:
        print("❌ 找不到 `gateway/app/steps/brief.py`，请检查 Cline 是否创建了文件。")
    except Exception as e:
        print(f"❌ 运行报错: {e}")
    finally:
        # 清理
        if os.path.exists("temp_subs.json"): os.remove("temp_subs.json")
        if os.path.exists("temp_brief_result.json"): os.remove("temp_brief_result.json")

if __name__ == "__main__":
    asyncio.run(verify_brief_step())