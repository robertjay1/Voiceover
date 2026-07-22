"""Kokoro — small, fast, very natural neural TTS that runs fully offline.

Kokoro-82M (Apache-2.0) is the naturalness sweet spot for local
narration: close to cloud-neural quality, real-time on a laptop CPU,
no API and no account. The model (~330 MB) downloads once from
Hugging Face on first use.

Install:  pip install voiceover[kokoro]   (or: pip install kokoro soundfile)

Voices are built in (af_heart, am_michael, bf_emma, ...). You can also
BLEND voices with weights to design your own — great for building a
custom voice bank:

    voiceover preview "Hello" --engine kokoro --voice "af_heart*0.6+af_sky*0.4"
    voiceover bank add my-signature --engine kokoro --voice "af_heart*0.6+af_sky*0.4"
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .base import EngineError, TTSEngine

DEFAULT_VOICE = "af_heart"
SAMPLE_RATE = 24000

# First letter of the voice name encodes the language pipeline:
# a=American English, b=British English, e=Spanish, f=French, h=Hindi,
# i=Italian, j=Japanese, p=Portuguese, z=Mandarin.
KNOWN_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_michael", "am_fenrir", "am_puck", "am_adam", "am_echo",
    "bf_emma", "bf_isabella", "bf_alice", "bm_george", "bm_lewis", "bm_daniel",
]


def parse_blend(spec: str) -> list[tuple[str, float]]:
    """Parse "af_heart*0.6+af_sky*0.4" (or "af_heart+af_sky") into
    [(name, weight), ...]. Weights default to equal and are normalized."""
    parts = []
    for piece in spec.split("+"):
        piece = piece.strip()
        if not piece:
            continue
        if "*" in piece:
            name, _, weight_text = piece.partition("*")
            try:
                weight = float(weight_text)
            except ValueError as exc:
                raise EngineError(f"Bad blend weight in {piece!r}") from exc
        else:
            name, weight = piece, 1.0
        if weight <= 0:
            raise EngineError(f"Blend weight must be positive in {piece!r}")
        parts.append((name.strip(), weight))
    if not parts:
        raise EngineError(f"Empty voice blend: {spec!r}")
    total = sum(w for _, w in parts)
    return [(name, weight / total) for name, weight in parts]


class KokoroEngine(TTSEngine):
    extension = "wav"

    def __init__(self, voice: str | None = None, rate: float = 1.0):
        if importlib.util.find_spec("kokoro") is None:
            raise EngineError(
                "The kokoro engine is not installed. Run: pip install voiceover[kokoro]\n"
                "(The ~330 MB model downloads automatically on first use.)"
            )
        self.voice = voice or DEFAULT_VOICE
        self.blend = parse_blend(self.voice)
        self.rate = rate
        self.lang_code = self.blend[0][0][0]  # first letter of first voice
        self._pipeline = None
        self._voice_ref = None

    def describe(self) -> str:
        return f"kokoro ({self.voice}, rate {self.rate})"

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        from kokoro import KPipeline

        self._pipeline = KPipeline(lang_code=self.lang_code)
        if len(self.blend) == 1:
            self._voice_ref = self.blend[0][0]
        else:
            # Weighted average of voice embeddings = a new custom voice.
            mixed = None
            for name, weight in self.blend:
                tensor = self._pipeline.load_voice(name)
                mixed = tensor * weight if mixed is None else mixed + tensor * weight
            self._voice_ref = mixed

    def synthesize(self, text: str, out_path: Path) -> None:
        self._load()
        import numpy as np
        import soundfile

        pieces = []
        for result in self._pipeline(text, voice=self._voice_ref, speed=self.rate):
            audio = result.audio if hasattr(result, "audio") else result[-1]
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            pieces.append(np.asarray(audio, dtype="float32"))
        if not pieces:
            raise EngineError("kokoro produced no audio")

        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        soundfile.write(str(tmp_path), np.concatenate(pieces), SAMPLE_RATE)
        tmp_path.replace(out_path)
