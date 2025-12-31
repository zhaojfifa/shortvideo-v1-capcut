from __future__ import annotations

from typing import Optional

from gateway.app.ports.storage import IStorageService

_storage_service: Optional[IStorageService] = None


def set_storage_service(service: IStorageService) -> None:
    global _storage_service
    _storage_service = service


def get_storage_service() -> IStorageService:
    if _storage_service is None:
        raise RuntimeError("Storage service is not configured")
    return _storage_service
