"""eSpeak NG — instant, fully offline, robotic-sounding.

Not audiobook quality, but perfect for fast previews (checking chapter
splits and pacing before an hours-long neural render) and for testing
the pipeline on machines with no network and no Piper models.

Install: apt install espeak-ng  /  brew install espeak-ng
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import EngineError, TTSEngine

DEFAULT_VOICE = "en-us"
BASE_WPM = 175


class EspeakEngine(TTSEngine):
    extension = "wav"

    def __init__(self, voice: str | None = None, rate: float = 1.0):
        self.binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if self.binary is None:
            raise EngineError(
                "espeak-ng not found. Install it with: apt install espeak-ng "
                "(Linux) or brew install espeak-ng (macOS)"
            )
        self.voice = voice or DEFAULT_VOICE
        self.wpm = max(80, round(BASE_WPM * rate))

    def describe(self) -> str:
        return f"espeak ({self.voice}, {self.wpm} wpm)"

    def synthesize(self, text: str, out_path: Path) -> None:
        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        cmd = [
            self.binary,
            "-v", self.voice,
            "-s", str(self.wpm),
            "-w", str(tmp_path),
            "--stdin",
        ]
        result = subprocess.run(
            cmd, input=text, capture_output=True, text=True, check=False
        )
        if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            detail = (result.stderr or result.stdout or "").strip()[-500:]
            raise EngineError(f"espeak failed (exit {result.returncode}): {detail}")
        tmp_path.replace(out_path)


def list_voices(language: str | None = None) -> str:
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if binary is None:
        raise EngineError("espeak-ng not found.")
    cmd = [binary, f"--voices={language}" if language else "--voices"]
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
