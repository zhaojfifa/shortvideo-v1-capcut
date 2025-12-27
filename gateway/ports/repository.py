from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

# 这是一个抽象基类（接口），定义了如何操作任务数据
class ITaskRepository(ABC):
    
    @abstractmethod
    def get(self, task_id: str) -> Optional[Any]:
        """根据 ID 获取任务"""
        pass

    @abstractmethod
    def update(self, task_id: str, updates: Dict[str, Any]) -> Any:
        """更新任务字段"""
        pass

    @abstractmethod
    def create(self, task_data: Dict[str, Any]) -> Any:
        """创建新任务"""
        pass
        
    @abstractmethod
    def list_tasks(self, limit: int = 20, offset: int = 0, filters: Dict = None) -> List[Any]:
        """获取任务列表"""
        pass