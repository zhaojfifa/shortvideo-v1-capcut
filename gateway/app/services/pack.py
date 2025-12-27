"""Compatibility shim for pack_service."""

from gateway.app.services.pack_service import PackError, create_capcut_pack

__all__ = ["PackError", "create_capcut_pack"]
