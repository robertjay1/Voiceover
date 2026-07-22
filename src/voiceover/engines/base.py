from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class EngineError(RuntimeError):
    """A TTS engine failed in a way the user needs to act on."""


class TTSEngine(ABC):
    """One narrator configuration: an engine plus voice/rate settings."""

    #: Audio container the engine produces ("mp3" or "wav").
    extension: str

    @abstractmethod
    def synthesize(self, text: str, out_path: Path) -> None:
        """Render text to audio at out_path (atomic: write temp, then rename)."""

    def describe(self) -> str:
        return type(self).__name__
