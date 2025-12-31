from abc import ABC, abstractmethod
from typing import Dict, Any

class IStorageService(ABC):
    @abstractmethod
    def upload_file(
        self,
        file_path: str,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        pass

    @abstractmethod
    def download_file(self, key: str, destination_path: str) -> None:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        content_type: str | None = None,
        filename: str | None = None,
        disposition: str | None = None,
    ) -> str:
        pass
