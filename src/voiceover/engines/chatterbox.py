"""Chatterbox — zero-shot voice cloning, running locally.

Resemble AI's Chatterbox (MIT license) clones a voice from a short
reference recording — about 10 seconds of clean speech — and narrates
any text in that voice, entirely on your machine. Output carries
Resemble's imperceptible Perth watermark, a responsible default for
synthetic speech.

Only clone voices you have the right to use: your own, or a speaker
who has given you permission.

Install:  pip install voiceover[clone]   (or: pip install chatterbox-tts)
Hardware: a GPU (CUDA or Apple Silicon) makes it pleasant; CPU works
          but is slow — fine for short texts, patient for books.

Typical use:

    voiceover clone my-voice --sample me.wav
    voiceover build book.md --voice my-voice --m4b
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .base import EngineError, TTSEngine

# Long inputs degrade cloning quality; the build pipeline caps chunk
# size to this for chatterbox.
PREFERRED_CHUNK_CHARS = 350


class ChatterboxEngine(TTSEngine):
    extension = "wav"
    preferred_chunk_chars = PREFERRED_CHUNK_CHARS

    _model = None  # class-level: load the ~2 GB model once per process

    def __init__(
        self,
        voice: str | None = None,  # unused; present for engine-API symmetry
        rate: float = 1.0,
        sample: str | None = None,
        exaggeration: float | None = None,
    ):
        if importlib.util.find_spec("chatterbox") is None:
            raise EngineError(
                "The chatterbox engine is not installed. "
                "Run: pip install voiceover[clone]"
            )
        self.sample = str(Path(sample).expanduser()) if sample else None
        if self.sample and not Path(self.sample).is_file():
            raise EngineError(f"Voice sample not found: {self.sample}")
        self.exaggeration = exaggeration
        if rate != 1.0:
            # Chatterbox has no speed control; the reference recording's
            # pace carries over instead.
            self.rate_note = " (rate ignored: pace follows the sample)"
        else:
            self.rate_note = ""

    def describe(self) -> str:
        source = Path(self.sample).name if self.sample else "built-in voice"
        return f"chatterbox (cloned from {source}){self.rate_note}"

    @classmethod
    def _load_model(cls):
        if cls._model is None:
            import torch
            from chatterbox.tts import ChatterboxTTS

            if torch.cuda.is_available():
                device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
            cls._model = ChatterboxTTS.from_pretrained(device=device)
        return cls._model

    def synthesize(self, text: str, out_path: Path) -> None:
        import torchaudio

        model = self._load_model()
        kwargs = {}
        if self.sample:
            kwargs["audio_prompt_path"] = self.sample
        if self.exaggeration is not None:
            kwargs["exaggeration"] = self.exaggeration
        wav = model.generate(text, **kwargs)

        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        torchaudio.save(str(tmp_path), wav, model.sr)
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise EngineError("chatterbox produced no audio")
        tmp_path.replace(out_path)
