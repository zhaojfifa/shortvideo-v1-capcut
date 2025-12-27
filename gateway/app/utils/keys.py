import os

class KeyBuilder:
    """
    统一生成对象存储路径 (Object Keys)
    强制格式: {tenant_id}/{project_id}/{task_id}/{artifact_name}
    """
    
    @staticmethod
    def build(tenant_id: str, project_id: str, task_id: str, artifact_name: str) -> str:
        # 确保不使用 tasks/task_id 这种旧格式
        # 如果 tenant_id 为空，回退到 default
        tenant = tenant_id or "default"
        project = project_id or "default"
        
        # 清理路径中的多余斜杠
        return f"{tenant}/{project}/{task_id}/{artifact_name}".replace("//", "/")

    @staticmethod
    def parse(key: str) -> dict:
        """
        从 key 反解出元数据 (用于调试或迁移)
        """
        parts = key.split("/")
        if len(parts) >= 4:
            return {
                "tenant_id": parts[0],
                "project_id": parts[1],
                "task_id": parts[2],
                "filename": parts[-1]
            }
        return {}