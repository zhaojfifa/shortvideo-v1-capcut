import os
import logging
import tempfile
from gateway.app.config import get_settings
from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.utils.keys import KeyBuilder
from pathlib import Path
from urllib.parse import unquote


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

def _local_path_from_file_url(key: str) -> Path | None:
    if not key or not isinstance(key, str):
        return None
    if not key.startswith("file://"):
        return None

    # handle Windows: file://D:/a/b or file:///D:/a/b
    p = key[len("file://"):]
    if p.startswith("/"):
        p = p.lstrip("/")  # tolerate file:///D:/...
    p = unquote(p)
    return Path(p)

# =========================================================
# 2. Legacy Wrappers (Hotfix for tasks.py / main.py compatibility)
# 这些是旧代码依赖的函数名，我们用新架构实现它们，保持接口不变。
# =========================================================

def upload_task_artifact(task, local_path, artifact_name, task_id=None, **kwargs):
    """
    Legacy wrapper: accept task object/dict and local file path, upload to storage.
    Compatible with routers/tasks.py and older call sites.
    """
    # 1) Resolve task_id
    t_id = (
        task_id
        or getattr(task, "task_id", None)
        or getattr(task, "id", None)
        or (task.get("task_id") if isinstance(task, dict) else None)
        or (task.get("id") if isinstance(task, dict) else None)
        or "unknown"
    )

    # 2) Resolve tenant/project
    tenant = (
        getattr(task, "tenant_id", None)
        or getattr(task, "tenant", None)
        or (task.get("tenant_id") if isinstance(task, dict) else None)
        or (task.get("tenant") if isinstance(task, dict) else None)
        or "default"
    )
    project = (
        getattr(task, "project_id", None)
        or getattr(task, "project", None)
        or (task.get("project_id") if isinstance(task, dict) else None)
        or (task.get("project") if isinstance(task, dict) else None)
        or "default"
    )

    # ✅ Correct argument order: (task_id, local_path, artifact_name, ...)
    return upload_artifact(
        str(t_id),
        str(local_path),
        str(artifact_name),
        tenant_id=str(tenant),
        project_id=str(project),
    )


def get_download_url(
    task_or_key: str,
    artifact_name: str | None = None,
    tenant_id: str = "default",
    project_id: str = "default",
    *,
    expiration: int = 3600,
    content_type: str | None = None,
    filename: str | None = None,
    disposition: str | None = None,
) -> str:
    """
    Backward compatible:
    - get_download_url(key)
    - get_download_url(task_id, artifact_name, tenant_id=..., project_id=...)
    """
    storage = get_storage_service()
    if artifact_name is None:
        # treat first arg as full storage key
        key = task_or_key
    else:
        key = KeyBuilder.build(tenant_id, project_id, task_or_key, artifact_name)
    try:
        return storage.generate_presigned_url(
            key,
            expiration=expiration,
            content_type=content_type,
            filename=filename,
            disposition=disposition,
        )
    except TypeError:
        return storage.generate_presigned_url(key, expiration=expiration)


def object_exists(task_or_key: str, artifact_name: str | None = None,
                  tenant_id: str = "default", project_id: str = "default") -> bool:
    storage = get_storage_service()

    if artifact_name is None:
        key = task_or_key

        # ✅ local file url shortcut
        lp = _local_path_from_file_url(key)
        if lp is not None:
            return lp.exists()

    else:
        key = KeyBuilder.build(tenant_id, project_id, task_or_key, artifact_name)

    return storage.exists(key)



def get_object_bytes(task_or_key: str, artifact_name: str | None = None,
                     tenant_id: str = "default", project_id: str = "default") -> bytes | None:
    import os
    import tempfile

    storage = get_storage_service()

    if artifact_name is None:
        key = task_or_key

        # ✅ local file url shortcut
        lp = _local_path_from_file_url(key)
        if lp is not None:
            try:
                return lp.read_bytes()
            except Exception as e:
                logger.error(f"Failed to read local file bytes from {lp}: {e}")
                return None
    else:
        key = KeyBuilder.build(tenant_id, project_id, task_or_key, artifact_name)

    fd, temp_path = tempfile.mkstemp()
    os.close(fd)
    try:
        storage.download_file(key, temp_path)
        with open(temp_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read bytes from {key}: {e}")
        return None
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
