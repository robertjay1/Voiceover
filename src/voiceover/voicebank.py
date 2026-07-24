"""Voice bank (reusable named voice profiles) and cast files (speaker -> voice).

The bank is your personal library of narrator voices — build it once,
reuse it across every book:

    voiceover bank add gruff-captain --engine edge --voice en-GB-RyanNeural --rate 0.92

A cast file maps the speakers found in a specific book to voices. Values
may be a bank profile name, a raw engine voice name, or an inline object:

    {
      "narrator": "en-US-AndrewMultilingualNeural",
      "Elias": "gruff-captain",
      "Mira": {"engine": "edge", "voice": "en-US-EmmaMultilingualNeural", "rate": 1.05}
    }

Speakers missing from the cast are auto-assigned distinct voices from a
per-engine pool, deterministically, in order of first appearance.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .engines import create_engine
from .engines.base import EngineError, TTSEngine

DEFAULT_BANK_PATH = Path("~/.voiceover/voicebank.json")

DEFAULT_VOICES = {
    "edge": "en-US-AndrewMultilingualNeural",
    "kokoro": "af_heart",
    "espeak": "en-us",
    "piper": "en_US-lessac-medium",
    "chatterbox": None,  # built-in voice unless a sample is given
}

# Distinct-sounding voices for auto-assignment, most natural first.
AUTO_POOLS = {
    "edge": [
        "en-US-AndrewMultilingualNeural",
        "en-US-AvaMultilingualNeural",
        "en-GB-RyanNeural",
        "en-US-EmmaMultilingualNeural",
        "en-GB-SoniaNeural",
        "en-US-BrianMultilingualNeural",
        "en-AU-NatashaNeural",
        "en-US-ChristopherNeural",
        "en-GB-MaisieNeural",
        "en-US-MichelleNeural",
        "en-AU-WilliamNeural",
        "en-IE-EmilyNeural",
    ],
    "kokoro": [
        "am_michael", "af_bella", "bm_george", "bf_emma", "am_fenrir",
        "af_nicole", "bm_lewis", "bf_isabella", "am_puck", "af_sky",
    ],
    "espeak": ["en-us", "en+f3", "en+m3", "en+f4", "en+m7", "en+f2", "en+croak"],
    # Piper voices are local model files and chatterbox voices are cloned
    # from samples; auto-assignment can't invent either, so speakers must
    # be cast explicitly (uncast ones share the narrator).
    "piper": [],
    "chatterbox": [],
}


@dataclass
class VoiceProfile:
    engine: str
    voice: str | None = None
    rate: float = 1.0
    volume: float = 1.0
    model_dir: str | None = None
    sample: str | None = None  # reference recording for cloned voices
    exaggeration: float | None = None  # chatterbox expressiveness (0..1)
    pitch: float = 1.0  # 1.0-centred multiplier (edge engine only)

    def key(self) -> str:
        """Stable identity used in chunk cache filenames."""
        raw = (f"{self.engine}:{self.voice}:{self.rate}:{self.volume}:"
               f"{self.sample}:{self.pitch}")
        return re.sub(r"[^\w+-]+", "_", raw)

    def create(self) -> TTSEngine:
        options: dict = {"voice": self.voice, "rate": self.rate}
        if self.engine == "edge":
            options["volume"] = self.volume
            options["pitch"] = self.pitch
        if self.engine == "piper":
            options["model_dir"] = self.model_dir
        if self.engine == "chatterbox":
            options["sample"] = self.sample
            options["exaggeration"] = self.exaggeration
        return create_engine(self.engine, **options)

    def label(self) -> str:
        rate = f" @{self.rate}x" if self.rate != 1.0 else ""
        if self.engine == "chatterbox":
            source = Path(self.sample).name if self.sample else "built-in"
            return f"chatterbox:cloned<{source}>{rate}"
        return f"{self.engine}:{self.voice}{rate}"


# ---------- Voice bank ----------


def slugify(name: str) -> str:
    """Character name -> stable bank key ('DS Anna Okoye' -> 'anna-okoye')."""
    name = re.sub(r"\b(?:mr|mrs|ms|mx|dr|miss|sir|lady|lord|prof|professor|"
                  r"dc|ds|di|dci|pc|sgt|detective|constable|sergeant|the|a|an)\b",
                  " ", name, flags=re.IGNORECASE)
    slug = re.sub(r"[^\w]+", "-", name.strip().lower()).strip("-")
    return slug or re.sub(r"[^\w]+", "-", name.strip().lower()).strip("-") or "voice"


def load_bank(path: Path | None = None, required: bool = False) -> dict[str, VoiceProfile]:
    """Load a voice bank. A missing default bank is simply empty, but a
    bank the user explicitly named must exist (required=True) — silently
    continuing would resolve profile names as literal voice names."""
    bank_path = Path(path or DEFAULT_BANK_PATH).expanduser()
    if not bank_path.is_file():
        if required:
            raise EngineError(
                f"Voice bank file not found: {bank_path}\n"
                "Check the filename (downloads are often saved as "
                "'voicebank (1).json') and the folder you're running from."
            )
        return {}
    data = json.loads(bank_path.read_text(encoding="utf-8"))
    return {name: VoiceProfile(**profile) for name, profile in data.items()}


def save_bank(bank: dict[str, VoiceProfile], path: Path | None = None) -> Path:
    bank_path = Path(path or DEFAULT_BANK_PATH).expanduser()
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    data = {name: asdict(profile) for name, profile in sorted(bank.items())}
    bank_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return bank_path


# ---------- Cast ----------


def _profile_from_spec(spec, bank: dict[str, VoiceProfile], default_engine: str) -> VoiceProfile:
    if isinstance(spec, dict):
        return VoiceProfile(**{"engine": default_engine, **spec})
    if isinstance(spec, str):
        if spec in bank:
            return bank[spec]
        # Edge voice names look like en-GB-RyanNeural; a dashless string
        # that isn't in the bank is almost certainly a bank-name typo (or
        # a bank that failed to load) — fail now, not after synthesis.
        if default_engine == "edge" and "-" not in spec:
            known = ", ".join(sorted(bank)) or "(bank is empty)"
            raise EngineError(
                f"Voice {spec!r} is not in the voice bank and doesn't look "
                f"like an engine voice name.\nBank profiles available: {known}"
            )
        return VoiceProfile(engine=default_engine, voice=spec)
    raise EngineError(f"Unrecognized voice spec: {spec!r}")


@dataclass
class Cast:
    """Resolves speaker names to voice profiles, auto-assigning the rest."""

    mapping: dict[str, VoiceProfile] = field(default_factory=dict)
    default_engine: str = "edge"
    narrator_profile: VoiceProfile | None = None
    _auto: dict[str, VoiceProfile] = field(default_factory=dict)
    _pool_index: int = 0

    @classmethod
    def load(
        cls,
        cast_path: Path | None,
        bank: dict[str, VoiceProfile],
        default_engine: str,
        narrator_profile: VoiceProfile,
    ) -> "Cast":
        mapping: dict[str, VoiceProfile] = {}
        if cast_path is not None:
            data = json.loads(Path(cast_path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise EngineError(f"Cast file {cast_path} must be a JSON object.")
            for speaker, spec in data.items():
                mapping[speaker] = _profile_from_spec(spec, bank, default_engine)
        return cls(
            mapping=mapping,
            default_engine=default_engine,
            narrator_profile=narrator_profile,
        )

    def profile_for(self, speaker: str) -> VoiceProfile:
        if speaker in self.mapping:
            return self.mapping[speaker]
        if speaker == "narrator":
            return self.narrator_profile
        if speaker in self._auto:
            return self._auto[speaker]

        pool = AUTO_POOLS.get(self.default_engine, [])
        taken = {p.voice for p in self.mapping.values()} | {self.narrator_profile.voice}
        while self._pool_index < len(pool) and pool[self._pool_index] in taken:
            self._pool_index += 1
        if self._pool_index < len(pool):
            profile = VoiceProfile(engine=self.default_engine, voice=pool[self._pool_index])
            self._pool_index += 1
        else:
            # Pool exhausted (or piper): minor characters share the narrator.
            profile = self.narrator_profile
        self._auto[speaker] = profile
        return profile

    def assignments(self) -> dict[str, VoiceProfile]:
        return {**self.mapping, **self._auto}
