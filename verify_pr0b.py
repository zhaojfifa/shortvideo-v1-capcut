import sys
import os
import time

# 确保能找到 gateway 模块
sys.path.append(os.getcwd())

def verify_adapter():
    print(">>> 开始验证 PR-0B (存储适配器 & 依赖注入)...")

    # 1. 验证模块结构 (Hexagonal Architecture)
    try:
        from gateway.app.config import get_storage_service, get_settings
        from gateway.app.ports.storage import IStorageService
        from gateway.app.adapters.storage_r2 import R2StorageService
        from gateway.app.utils.keys import KeyBuilder
        print("✅ 模块结构验证通过 (Ports, Adapters, KeyBuilder 均存在)")
    except ImportError as e:
        print(f"❌ 模块缺失: {e}")
        return

    # 2. 验证工厂模式 (Factory)
    try:
        settings = get_settings()
        print(f"当前配置 STORAGE_BACKEND: {settings.STORAGE_BACKEND}")
        
        # 获取实例
        storage = get_storage_service()
        print(f"✅ 服务实例化成功: {type(storage).__name__}")
        
        # 检查类型是否匹配配置
        if settings.STORAGE_BACKEND == "s3" and not isinstance(storage, R2StorageService):
            print("❌ 错误：配置为 s3 但未返回 R2StorageService")
            return
    except Exception as e:
        print(f"❌ 实例化失败: {e}")
        return

    # 3. 集成测试 (上传/下载流程)
    tenant = "verify_tenant"
    project = "verify_proj"
    task_id = f"task_{int(time.time())}"
    filename = "adapter_test.txt"
    target_key = KeyBuilder.build(tenant, project, task_id, filename)
    
    print(f"测试目标路径: {target_key}")
    
    # 创建临时文件
    with open(filename, "w") as f:
        f.write("PR-0B Adapter Pattern Verification Data")

    try:
        # A. 上传
        print("正在调用 storage.upload_file ...")
        url = storage.upload_file(filename, target_key)
        print(f"✅ 上传成功! Public URL: {url}")

        # B. 检查存在性
        exists = storage.exists(target_key)
        print(f"✅ Exists 检查: {exists}")
        if not exists:
            print("❌ 文件上传后检测不到！")
            return

        # C. 获取签名链接 (Presigned URL)
        signed_url = storage.generate_presigned_url(target_key)
        print(f"✅ 签名链接生成成功: {signed_url[:60]}...")

        # D. 下载回本地
        download_path = "adapter_download_check.txt"
        storage.download_file(target_key, download_path)
        if os.path.exists(download_path):
            print("✅ 下载成功")
        else:
            print("❌ 下载失败")
            
    except Exception as e:
        print(f"❌ 操作测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理垃圾
        if os.path.exists(filename): os.remove(filename)
        if os.path.exists("adapter_download_check.txt"): os.remove("adapter_download_check.txt")

if __name__ == "__main__":
    verify_adapter()