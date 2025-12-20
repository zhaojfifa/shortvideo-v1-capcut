from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Protocol

from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)


class ParseProvider(Protocol):
    async def run(self, payload: Any) -> Any: ...


class SubtitlesProvider(Protocol):
    async def run(self, payload: Any) -> Any: ...


class DubProvider(Protocol):
    async def run(self, payload: Any) -> Any: ...


class PackProvider(Protocol):
    async def run(self, payload: Any) -> Any: ...


class FaceSwapProvider(Protocol):
    async def run(self, payload: Any) -> Any: ...


@dataclass
class Provider:
    name: str
    run: Callable[[Any], Any]


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, Dict[str, Provider]] = {}

    def register(self, tool_type: str, provider: Provider) -> None:
        self._providers.setdefault(tool_type, {})[provider.name] = provider

    def get(self, tool_type: str, name: str) -> Provider:
        if tool_type not in self._providers or name not in self._providers[tool_type]:
            raise KeyError(f"Provider not found: {tool_type}:{name}")
        return self._providers[tool_type][name]

    def list(self) -> Dict[str, list[str]]:
        return {
            tool_type: sorted(providers.keys())
            for tool_type, providers in self._providers.items()
        }


registry = ProviderRegistry()


def get_provider(tool_type: str, name: str) -> Provider:
    return registry.get(tool_type, name)


registry.register("parse", Provider(name="xiongmao", run=run_parse_step))
registry.register("subtitles", Provider(name="gemini", run=run_subtitles_step))
registry.register("dub", Provider(name="lovo", run=run_dub_step))
registry.register("pack", Provider(name="capcut", run=run_pack_step))


async def face_swap_stub(_payload: Any) -> dict:
    return {"detail": "not implemented"}


registry.register("face_swap", Provider(name="none", run=face_swap_stub))
