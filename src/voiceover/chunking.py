"""Split chapter text into synthesis-sized chunks.

TTS engines behave best on bounded inputs: cloud engines have request
limits, and chunking gives us resumability — a crashed 8-hour job picks
up at the last finished chunk instead of starting over.

Chunks break at paragraph boundaries when possible, then sentence
boundaries, so prosody stays natural across the seams.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 1800

# Sentence end: terminal punctuation (with optional closing quote/paren)
# followed by whitespace, not followed by a lowercase letter — so a
# dialogue tag like «"Stop!" she said.» stays one sentence. Deliberately
# simple — a missed abbreviation only shifts a chunk boundary, it never
# loses text. The separator is captured so closing quotes can be
# re-attached to their sentence.
_SENTENCE_END = re.compile(r"((?<=[.!?…])[\"'”’)\]]*\s+)(?![a-z])")


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_END.split(text)
    sentences = []
    for i in range(0, len(parts), 2):
        separator = parts[i + 1] if i + 1 < len(parts) else ""
        sentence = (parts[i] + separator.rstrip()).strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Hard-split a sentence longer than max_chars, preferring commas, then spaces."""
    pieces = []
    rest = sentence
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cut = window.rfind(", ")
        if cut < max_chars // 4:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = max_chars
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip(", ").strip()
    if rest:
        pieces.append(rest)
    return pieces


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split text into chunks of at most max_chars, breaking at natural seams."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    def add(piece: str, separator: str) -> None:
        nonlocal current
        if current and len(current) + len(separator) + len(piece) > max_chars:
            flush()
        current = f"{current}{separator}{piece}" if current else piece

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            add(paragraph, "\n\n")
            continue
        for sentence in split_sentences(paragraph):
            if len(sentence) <= max_chars:
                add(sentence, " ")
            else:
                for piece in _split_long_sentence(sentence, max_chars):
                    add(piece, " ")
    flush()
    return chunks
