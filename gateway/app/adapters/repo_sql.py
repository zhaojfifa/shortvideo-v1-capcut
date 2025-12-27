from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from gateway.ports.repository import ITaskRepository
from gateway.app.models import Task

class SQLAlchemyTaskRepository(ITaskRepository):
    def __init__(self, session: Session):
        self.session = session

    def get(self, task_id: str) -> Optional[Task]:
        return self.session.query(Task).filter(Task.id == task_id).first()

    def update(self, task_id: str, updates: Dict[str, Any]) -> Task:
        task = self.get(task_id)
        if task:
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            self.session.commit()
            self.session.refresh(task)
        return task

    def create(self, task: Task) -> Task:
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def list_tasks(self, limit: int = 20, offset: int = 0, filters: Dict = None) -> List[Task]:
        query = self.session.query(Task)
        # 这里可以添加 filter 逻辑
        return query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()
