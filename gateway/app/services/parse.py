"""Compatibility shim for steps.parse."""

from gateway.app.steps.parse import detect_platform, parse_douyin_video, parse_video

__all__ = ["detect_platform", "parse_douyin_video", "parse_video"]
