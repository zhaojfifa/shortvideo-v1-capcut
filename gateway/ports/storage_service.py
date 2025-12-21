"""Port interface for artifact storage (upload + download URL resolution)."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class IStorageService(Protocol):
    """Storage abstraction for uploading artifacts and resolving download URLs."""

    def upload_file(self, local_path: str, key: str, content_type: Optional[str] = None) -> str:
        """Upload a local file to storage and return the resolved object key."""

    def get_download_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a download URL for an object key (may be presigned or public)."""

    def exists(self, key: str) -> bool:
        """Return True if the object key exists in storage."""
