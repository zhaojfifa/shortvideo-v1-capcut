import sys
import os

# 把当前目录加入路径，确保能 import gateway
sys.path.append(os.getcwd())

def verify():
    print(">>> 开始验证 PR-0A (基建收口)...")
    
    # 1. 验证 KeyBuilder 是否存在
    try:
        from gateway.app.utils.keys import KeyBuilder
        key = KeyBuilder.build("tenant1", "proj1", "task1", "file.mp4")
        print(f"✅ KeyBuilder 正常工作: {key}")
        if key != "tenant1/proj1/task1/file.mp4":
            print("❌ 路径格式不对！")
    except ImportError:
        print("❌ KeyBuilder 模块缺失！(请检查 gateway/app/utils/keys.py)")
        return

    # 2. 验证 Task Model 字段是否更新
    try:
        from gateway.app.models import Task
        # 检查新字段是否存在
        if hasattr(Task, 'tenant_id') and hasattr(Task, 'target_lang') and hasattr(Task, 'origin_srt_path'):
            print("✅ Task Model 字段验证通过 (tenant_id, target_lang 已存在)")
        else:
            print("❌ Task Model 缺少关键字段！请检查 models.py")
            # 打印出来看看缺啥
            print(f"当前字段: {[c.name for c in Task.__table__.columns]}")
    except ImportError:
        print("❌ 无法导入 Task Model！")
        return

    # 3. 验证 Storage 逻辑语法
    try:
        from gateway.app.services.artifact_storage import upload_artifact
        print("✅ Artifact Storage 语法检查通过")
    except ImportError as e:
        print(f"❌ Artifact Storage 代码有误: {e}")

if __name__ == "__main__":
    verify()