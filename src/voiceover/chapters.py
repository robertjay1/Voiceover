"""Split source text into chapters for audiobook production."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Markdown ATX headings, level 1-2 ("# Title" / "## Title").
_MD_HEADING = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$", re.MULTILINE)

# Plain-text chapter openers on their own line: "Chapter 1", "CHAPTER XII",
# "Part Two: The Return", "Prologue", "Epilogue".
_PLAIN_HEADING = re.compile(
    r"^[ \t]*((?:chapter|part)\s+(?:\d+|[ivxlcdm]+|\w+)(?:\s*[:.—-]\s*\S.*)?"
    r"|prologue|epilogue|introduction|foreword|afterword)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".text"}


@dataclass
class Chapter:
    title: str
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax that a narrator should not read aloud."""
    # Fenced code blocks: keep the content, drop the fences.
    text = re.sub(r"^```.*$", "", text, flags=re.MULTILINE)
    # Images: drop entirely. Links: keep the label.
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # Emphasis and inline code markers.
    text = re.sub(r"(\*{1,3}|_{1,3}|`)(.+?)\1", r"\2", text)
    # Blockquote markers and horizontal rules.
    text = re.sub(r"^[ \t]*>[ \t]?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*([-*_][ \t]*){3,}$", "", text, flags=re.MULTILINE)
    # List bullets become plain sentences.
    text = re.sub(r"^[ \t]*[-*+][ \t]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*\d+[.)][ \t]+", "", text, flags=re.MULTILINE)
    return text


def _split_on(pattern: re.Pattern, text: str, title_group: int) -> list[Chapter]:
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    chapters: list[Chapter] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        chapters.append(Chapter(title="Preamble", text=preamble))

    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        title = match.group(title_group).strip()
        if body:
            chapters.append(Chapter(title=title, text=body))
    return chapters


def split_chapters(text: str, markdown: bool = True) -> list[Chapter]:
    """Split raw text into chapters.

    Tries markdown headings first, then plain-text "Chapter N" style
    openers; falls back to a single chapter containing everything.
    """
    if markdown:
        chapters = _split_on(_MD_HEADING, text, title_group=2)
        if chapters:
            return [Chapter(c.title, _strip_markdown(c.text).strip()) for c in chapters]
        text = _strip_markdown(text)

    chapters = _split_on(_PLAIN_HEADING, text, title_group=1)
    if chapters:
        return chapters

    stripped = text.strip()
    return [Chapter(title="Full Text", text=stripped)] if stripped else []


def load_chapters(path: Path) -> list[Chapter]:
    """Load chapters from a file, or from a directory of one-file-per-chapter."""
    path = Path(path)
    if path.is_dir():
        files = sorted(
            p for p in path.iterdir() if p.suffix.lower() in TEXT_SUFFIXES and p.is_file()
        )
        if not files:
            raise FileNotFoundError(f"No .txt/.md files found in directory: {path}")
        chapters = []
        for file in files:
            text = file.read_text(encoding="utf-8", errors="replace")
            is_md = file.suffix.lower() in {".md", ".markdown"}
            parts = split_chapters(text, markdown=is_md)
            body = "\n\n".join(p.text for p in parts).strip()
            # Prefer the file's own heading as the title, else its name.
            title = parts[0].title if len(parts) == 1 and parts[0].title != "Full Text" else None
            if title is None:
                title = re.sub(r"^\d+[\s._-]*", "", file.stem).replace("_", " ").strip() or file.stem
            if body:
                chapters.append(Chapter(title=title, text=body))
        return chapters

    if not path.is_file():
        raise FileNotFoundError(f"Input not found: {path}")
    if path.suffix.lower() == ".epub":
        from .epub import load_epub_chapters

        return load_epub_chapters(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    is_md = path.suffix.lower() in {".md", ".markdown"}
    return split_chapters(text, markdown=is_md)
