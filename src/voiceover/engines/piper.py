"""Piper — fast neural TTS that runs fully offline on CPU.

Voices are .onnx models downloaded once (e.g. en_US-lessac-medium), then
synthesis needs no network at all — ideal for long books and privacy.

Install:  pip install piper-tts
Voices:   python -m piper.download_voices en_US-lessac-medium --data-dir ~/piper-voices
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import EngineError, TTSEngine

DEFAULT_VOICE = "en_US-lessac-medium"


class PiperEngine(TTSEngine):
    extension = "wav"

    def __init__(
        self,
        voice: str | None = None,
        rate: float = 1.0,
        model_dir: str | Path | None = None,
    ):
        if shutil.which("piper") is None:
            raise EngineError(
                "The 'piper' command was not found. Install it with: pip install piper-tts"
            )
        self.voice = voice or DEFAULT_VOICE
        # Piper's length_scale stretches phoneme duration: 2.0 = half speed.
        self.length_scale = 1.0 / max(rate, 0.1)
        self.model_dir = Path(model_dir).expanduser() if model_dir else Path.cwd()
        self.model_path = self._resolve_model()

    def _resolve_model(self) -> Path:
        candidate = Path(self.voice).expanduser()
        if candidate.suffix == ".onnx" and candidate.is_file():
            return candidate
        found = list(self.model_dir.rglob(f"{self.voice}.onnx"))
        if found:
            return found[0]
        raise EngineError(
            f"Piper voice model '{self.voice}.onnx' not found in {self.model_dir}.\n"
            f"Download it with:\n"
            f"  python -m piper.download_voices {self.voice} --data-dir {self.model_dir}\n"
            f"or pass --model-dir pointing at your voices directory."
        )

    def describe(self) -> str:
        return f"piper ({self.model_path.stem}, length_scale {self.length_scale:.2f})"

    def synthesize(self, text: str, out_path: Path) -> None:
        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        cmd = [
            "piper",
            "--model", str(self.model_path),
            "--output-file", str(tmp_path),
            "--length-scale", f"{self.length_scale:.3f}",
            "--sentence-silence", "0.4",
        ]
        result = subprocess.run(
            cmd, input=text, capture_output=True, text=True, check=False
        )
        if result.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            detail = (result.stderr or result.stdout or "").strip()[-500:]
            raise EngineError(f"piper failed (exit {result.returncode}): {detail}")
        tmp_path.replace(out_path)
