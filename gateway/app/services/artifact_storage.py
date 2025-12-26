import os
import logging
import tempfile
from gateway.app.config import get_settings, get_storage_service
from gateway.app.utils.keys import KeyBuilder

# 允许本地开发没装 boto3 时不崩
try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)

# =========================================================
# 1. New Architecture Core Functions (Recommended)
# =========================================================

def upload_artifact(task_id: str, local_path: str, artifact_name: str, 
                   tenant_id: str = "default", project_id: str = "default") -> str | None:
    """上传文件到存储 (Standard)"""
    storage = get_storage_service()
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    logger.info(f"Uploading {local_path} -> {key}")
    return storage.upload_file(local_path, key)

def download_artifact(task_id: str, artifact_name: str, local_path: str,
                     tenant_id: str = "default", project_id: str = "default") -> bool:
    """下载文件到本地 (Standard)"""
    storage = get_storage_service()
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    try:
        storage.download_file(key, local_path)
        return True
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False

# =========================================================
# 2. Legacy Wrappers (Hotfix for tasks.py / main.py compatibility)
# 这些是旧代码依赖的函数名，我们用新架构实现它们，保持接口不变。
# =========================================================

def upload_task_artifact(task, local_path, artifact_name, task_id=None, **kwargs):
    """
    兼容旧的 upload_task_artifact 调用。
    参数 task 可能是 ORM 对象或字典，也可能传了 task_id。
    """
    # 尝试解析 ID 和租户信息
    t_id = task_id or getattr(task, "id", None) or (task.get("id") if isinstance(task, dict) else "unknown")
    
    # 尝试获取租户信息 (如果 task 对象里没有，就由 KeyBuilder 使用默认值)
    tenant = getattr(task, "tenant_id", "default")
    project = getattr(task, "project_id", "default")
    
    return upload_artifact(str(local_path), artifact_name, tenant_id=tenant, project_id=project, task_id=t_id)

def get_download_url(task_id: str, artifact_name: str, tenant_id: str = "default", project_id: str = "default") -> str:
    """
    兼容旧的 get_download_url 调用。返回签名链接。
    """
    storage = get_storage_service()
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    # 默认 1 小时有效期
    return storage.generate_presigned_url(key, expiration=3600)

def object_exists(task_id: str, artifact_name: str, tenant_id: str = "default", project_id: str = "default") -> bool:
    """
    兼容旧的 object_exists 调用。
    """
    storage = get_storage_service()
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    return storage.exists(key)

def get_object_bytes(task_id: str, artifact_name: str, tenant_id: str = "default", project_id: str = "default") -> bytes | None:
    """
    兼容旧的 get_object_bytes 调用。下载到临时文件读取后返回二进制。
    """
    storage = get_storage_service()
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    
    # 创建临时文件
    fd, temp_path = tempfile.mkstemp()
    os.close(fd) # 关闭句柄，让 storage 服务去写
    
    try:
        storage.download_file(key, temp_path)
        with open(temp_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read bytes from {key}: {e}")
        return None
    finally:
        # 清理垃圾
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass