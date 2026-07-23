"""Microsoft Edge neural voices (free, online, no API key).

High-quality neural voices in 90+ languages — the default engine for
audiobook production. Requires an internet connection.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .base import EngineError, TTSEngine

# The multilingual voices are Microsoft's newest generation and sound
# noticeably more natural for long-form narration than the older
# per-locale voices.
DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
RETRIES = 4
RETRY_DELAY = 2.0  # seconds, doubled on each retry


def _percent(value: float) -> str:
    """Map a 1.0-centred multiplier to edge-tts's signed percent string."""
    return f"{round((value - 1.0) * 100):+d}%"


class EdgeEngine(TTSEngine):
    extension = "mp3"

    def __init__(
        self,
        voice: str | None = None,
        rate: float = 1.0,
        volume: float = 1.0,
        pitch: float = 1.0,
    ):
        self.voice = voice or DEFAULT_VOICE
        self.rate = _percent(rate)
        self.volume = _percent(volume)
        # 1.0-centred multiplier -> Hz offset (speech f0 is ~120-220 Hz,
        # so 0.1 ≈ 15 Hz reads as a clearly different-but-same-accent voice).
        self.pitch = f"{round((pitch - 1.0) * 150):+d}Hz"

    def describe(self) -> str:
        extras = f", pitch {self.pitch}" if self.pitch != "+0Hz" else ""
        return f"edge ({self.voice}, rate {self.rate}{extras})"

    def synthesize(self, text: str, out_path: Path) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise EngineError("edge-tts is not installed. Run: pip install edge-tts") from exc

        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        last_error: Exception | None = None
        for attempt in range(RETRIES):
            if attempt:
                time.sleep(RETRY_DELAY * 2 ** (attempt - 1))
            try:
                communicate = edge_tts.Communicate(
                    text, self.voice, rate=self.rate, volume=self.volume,
                    pitch=self.pitch,
                )
                asyncio.run(communicate.save(str(tmp_path)))
                if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                    raise EngineError("engine produced no audio")
                tmp_path.replace(out_path)
                return
            except Exception as exc:  # noqa: BLE001 — network errors vary widely
                last_error = exc
                tmp_path.unlink(missing_ok=True)
        raise EngineError(
            f"edge-tts failed after {RETRIES} attempts: {last_error}. "
            "Check your internet connection, or try --engine piper for offline use."
        ) from last_error


def list_voices(language: str | None = None) -> list[dict]:
    try:
        import edge_tts
    except ImportError as exc:
        raise EngineError("edge-tts is not installed. Run: pip install edge-tts") from exc

    voices = asyncio.run(edge_tts.list_voices())
    if language:
        needle = language.lower()
        voices = [v for v in voices if needle in v["Locale"].lower()]
    return sorted(voices, key=lambda v: (v["Locale"], v["ShortName"]))
