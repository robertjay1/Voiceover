"""User pronunciation dictionary, applied to text before synthesis.

Neural TTS voices mispronounce unusual names and jargon (Halvorsen,
Okoye, Dufresne, digoxin). A lexicon maps a term to a phonetic
respelling that the engine reads correctly:

    { "Okoye": "oh-KOY-eh", "digoxin": "dij-OKS-in", "Dufresne": "doo-FRAYN" }

Matching is whole-word and case-insensitive; the respelling is
substituted verbatim, so capitalisation in the value controls stress.
Because substitution happens before chunk hashing, editing the lexicon
re-renders only the affected lines on the next run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_LEXICON_PATH = Path("~/.voiceover/lexicon.json")


def load_lexicon(path: Path | None = None, required: bool = False) -> dict[str, str]:
    lex_path = Path(path or DEFAULT_LEXICON_PATH).expanduser()
    if not lex_path.is_file():
        if required:
            raise FileNotFoundError(f"Pronunciation dictionary not found: {lex_path}")
        return {}
    data = json.loads(lex_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Lexicon {lex_path} must be a JSON object of term: pronunciation.")
    return {str(k): str(v) for k, v in data.items()}


def save_lexicon(entries: dict[str, str], path: Path | None = None) -> Path:
    lex_path = Path(path or DEFAULT_LEXICON_PATH).expanduser()
    lex_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: entries[k] for k in sorted(entries, key=str.lower)}
    lex_path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    return lex_path


class Lexicon:
    """Compiled pronunciation replacer."""

    def __init__(self, entries: dict[str, str]):
        self.entries = entries
        # Longest terms first so multi-word entries win over their parts.
        terms = sorted((t for t in entries if t.strip()), key=len, reverse=True)
        self._pattern = None
        if terms:
            # \b doesn't fire next to apostrophes/hyphens, so bound with
            # explicit non-word lookarounds that still allow those inside.
            alternation = "|".join(re.escape(t) for t in terms)
            self._pattern = re.compile(rf"(?<!\w)({alternation})(?!\w)", re.IGNORECASE)
            self._lookup = {t.lower(): entries[t] for t in terms}

    def apply(self, text: str) -> str:
        if not self._pattern:
            return text
        return self._pattern.sub(lambda m: self._lookup[m.group(0).lower()], text)

    def __bool__(self) -> bool:
        return bool(self._pattern)
