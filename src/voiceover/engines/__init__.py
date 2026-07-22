"""TTS engine registry."""

from __future__ import annotations

from .base import TTSEngine, EngineError

ENGINE_NAMES = ("edge", "piper", "espeak")


def create_engine(name: str, **options) -> TTSEngine:
    if name == "edge":
        from .edge import EdgeEngine

        return EdgeEngine(**options)
    if name == "piper":
        from .piper import PiperEngine

        return PiperEngine(**options)
    if name == "espeak":
        from .espeak import EspeakEngine

        return EspeakEngine(**options)
    raise EngineError(f"Unknown engine {name!r}. Available: {', '.join(ENGINE_NAMES)}")


__all__ = ["TTSEngine", "EngineError", "create_engine", "ENGINE_NAMES"]
