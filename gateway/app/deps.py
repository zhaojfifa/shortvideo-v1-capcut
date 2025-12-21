"""Dependency provider stubs for Phase0 ports (no runtime behavior change)."""

from __future__ import annotations

import os

from gateway.ports.pipeline_runner import IPipelineRunner
from gateway.ports.storage_service import IStorageService
from gateway.ports.task_repository import ITaskRepository


TASK_REPO_BACKEND = os.getenv("TASK_REPO_BACKEND", "").lower()


def get_task_repository() -> ITaskRepository:
    """Return the task repository implementation (Phase0 stub)."""
    if TASK_REPO_BACKEND == "s3":
        from gateway.adapters.task_repository_s3 import S3TaskRepository

        return S3TaskRepository()
    raise RuntimeError("Task repository provider not wired yet (Phase0 stub)")


def get_storage_service() -> IStorageService:
    """Return the storage service implementation (Phase0 stub)."""
    raise RuntimeError("Storage service provider not wired yet (Phase0 stub)")


def get_pipeline_runner() -> IPipelineRunner:
    """Return the pipeline runner implementation (Phase0 stub)."""
    raise RuntimeError("Pipeline runner provider not wired yet (Phase0 stub)")
