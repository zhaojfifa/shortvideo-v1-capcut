"""Port interface for pipeline execution orchestration."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IPipelineRunner(Protocol):
    """Pipeline runner abstraction for executing task steps."""

    def run(self, task_id: str, steps: list[str], **kwargs: Any) -> Any:
        """Run a set of pipeline steps for the given task and return a result."""
