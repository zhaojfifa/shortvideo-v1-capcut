"""Settings convenience module for FastAPI components."""
from gateway.app.config import Settings, get_settings, settings  # re-export

__all__ = ["Settings", "get_settings", "settings"]
