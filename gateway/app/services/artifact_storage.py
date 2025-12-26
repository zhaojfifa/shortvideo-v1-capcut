import os
import logging
from gateway.app.config import get_settings
# 假设你已经在 PR-0A 第一步创建了 keys.py，如果没有，请确保该文件存在
from gateway.app.utils.keys import KeyBuilder 

# 尝试导入 boto3，如果是在本地没装环境，允许失败（只要不调用就不会崩）
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

logger = logging.getLogger(__name__)

def get_s3_client():
    settings = get_settings()
    if not settings.R2_ACCESS_KEY or not settings.R2_SECRET_KEY:
        logger.warning("R2 credentials not set.")
        return None
    
    return boto3.client(
        's3',
        endpoint_url=settings.R2_ENDPOINT,
        aws_access_key_id=settings.R2_ACCESS_KEY,
        aws_secret_access_key=settings.R2_SECRET_KEY,
        region_name="auto"
    )

def storage_available() -> bool:
    return get_s3_client() is not None

def upload_artifact(task_id: str, local_path: str, artifact_name: str, 
                   tenant_id: str = "default", project_id: str = "default") -> str | None:
    """
    上传文件到 R2，使用标准命名空间。
    返回 Presigned URL 或 Public URL。
    """
    client = get_s3_client()
    if not client:
        return None

    settings = get_settings()
    bucket = settings.R2_BUCKET_NAME
    
    # === 核心修改：使用 KeyBuilder 生成路径 ===
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    # =======================================

    try:
        logger.info(f"Uploading {local_path} to {key}")
        client.upload_file(local_path, bucket, key)
        
        # 生成一个临时下载链接 (1小时有效) 用于回显
        url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=3600
        )
        return url
    except Exception as e:
        logger.error(f"Failed to upload artifact {key}: {e}")
        return None

def download_artifact(task_id: str, artifact_name: str, local_path: str,
                     tenant_id: str = "default", project_id: str = "default") -> bool:
    """
    从 R2 下载文件到本地。
    """
    client = get_s3_client()
    if not client:
        return False

    settings = get_settings()
    bucket = settings.R2_BUCKET_NAME
    
    # === 核心修改：使用 KeyBuilder ===
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    # ===============================

    try:
        # 确保本地目录存在
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        logger.info(f"Downloading {key} to {local_path}")
        client.download_file(bucket, key, local_path)
        return True
    except Exception as e:
        logger.error(f"Failed to download artifact {key}: {e}")
        # 兼容性尝试：如果新路径失败，尝试旧路径 (Fallback)
        try:
            old_key = f"tasks/{task_id}/{artifact_name}"
            logger.warning(f"Trying fallback key: {old_key}")
            client.download_file(bucket, old_key, local_path)
            return True
        except Exception as fallback_e:
            logger.error(f"Fallback download also failed: {fallback_e}")
            return False

def exists_in_storage(task_id: str, artifact_name: str,
                     tenant_id: str = "default", project_id: str = "default") -> bool:
    client = get_s3_client()
    if not client:
        return False
        
    settings = get_settings()
    bucket = settings.R2_BUCKET_NAME
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except:
        return False

# ============================================================
# Legacy Wrapper (Hotfix for Main.py compatibility)
# ============================================================
def get_download_url(task_id: str, artifact_name: str, tenant_id: str = "default", project_id: str = "default") -> str:
    """
    获取下载链接的兼容性包装器。
    供 main.py 和旧路由调用，底层转发给新的 Storage Service。
    """
    # 在函数内部导入，防止循环依赖
    from gateway.app.config import get_storage_service
    from gateway.app.utils.keys import KeyBuilder
    
    storage = get_storage_service()
    key = KeyBuilder.build(tenant_id, project_id, task_id, artifact_name)
    
    # 生成 1 小时有效的签名链接
    return storage.generate_presigned_url(key, expiration=3600)    
