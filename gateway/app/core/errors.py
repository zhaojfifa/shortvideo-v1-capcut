from typing import Optional


class SubtitlesError(Exception):
    """Raised when Step2 (subtitles pipeline) fails in a recoverable way."""

    def __init__(self, message: str, *, cause: Optional[BaseException] = None):
        super().__init__(message)
        self.message = message
        self.cause = cause
