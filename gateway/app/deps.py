"""Dependency provider stubs for Phase0 ports (TaskRepository wiring)."""

from __future__ import annotations

import logging
import os

from gateway.adapters.task_repository_file import FileTaskRepository
from gateway.adapters.task_repository_s3 import S3TaskRepository
from gateway.ports.pipeline_runner import IPipelineRunner
from gateway.ports.storage_service import IStorageService
from gateway.ports.task_repository import ITaskRepository

logger = logging.getLogger(__name__)
_repo_backend_logged = False


def _log_repo_backend_once(backend_label: str) -> None:
    global _repo_backend_logged
    if _repo_backend_logged:
        return
    logger.info("TASK_REPO_BACKEND=%s", backend_label)
    _repo_backend_logged = True


def get_task_repository() -> ITaskRepository:
    """Return the task repository implementation (Phase0 selector)."""
    backend = (os.getenv("TASK_REPO_BACKEND") or os.getenv("STORAGE_BACKEND") or "").lower()
    backend_label = backend or "file"
    _log_repo_backend_once(backend_label)
    if backend in {"s3", "r2"}:
        return S3TaskRepository()
    return FileTaskRepository()


def get_storage_service() -> IStorageService:
    """Return the storage service implementation (Phase0 stub)."""
    raise RuntimeError("Storage service provider not wired yet (Phase0 stub)")


def get_pipeline_runner() -> IPipelineRunner:
    """Return the pipeline runner implementation (Phase0 stub)."""
    raise RuntimeError("Pipeline runner provider not wired yet (Phase0 stub)")
