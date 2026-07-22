"""The audiobook build pipeline: chapters -> chunks -> audio -> book."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import audio
from .chapters import Chapter, load_chapters
from .chunking import chunk_text
from .engines.base import TTSEngine


@dataclass
class BuildResult:
    chapter_files: list[Path] = field(default_factory=list)
    book_file: Path | None = None
    chunks_total: int = 0
    chunks_reused: int = 0
    seconds_elapsed: float = 0.0


def _safe_filename(name: str, max_length: int = 60) -> str:
    name = re.sub(r"[^\w\s.-]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:max_length].strip() or "untitled"


def build_audiobook(
    input_path: Path,
    out_dir: Path,
    engine: TTSEngine,
    *,
    title: str | None = None,
    author: str | None = None,
    make_m4b: bool = False,
    single_file: bool = False,
    max_chunk_chars: int = 1800,
    resume: bool = True,
    log=print,
) -> BuildResult:
    """Render input text into per-chapter audio files, optionally combined.

    Chunk audio is cached in <out_dir>/.chunks/; re-running after a crash
    or interruption reuses every finished chunk (resume=True).
    """
    started = time.monotonic()
    input_path = Path(input_path)
    out_dir = Path(out_dir)
    chapters = load_chapters(input_path)
    if not chapters:
        raise ValueError(f"No readable text found in {input_path}")

    book_title = title or _title_from_input(input_path, chapters)
    ext = engine.extension
    work_dir = out_dir / ".chunks"
    result = BuildResult()

    total_words = sum(c.words for c in chapters)
    log(f"Narrating: {book_title}")
    log(f"Engine:    {engine.describe()}")
    log(f"Chapters:  {len(chapters)}  ({total_words:,} words)")

    for index, chapter in enumerate(chapters, start=1):
        chunks = chunk_text(chapter.text, max_chunk_chars)
        chapter_stem = f"{index:02d} - {_safe_filename(chapter.title)}"
        chapter_file = out_dir / f"{chapter_stem}.{ext}"
        chunk_dir = work_dir / f"ch{index:03d}"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        log(f"[{index}/{len(chapters)}] {chapter.title} — {len(chunks)} chunk(s)")

        chunk_files: list[Path] = []
        for chunk_index, chunk in enumerate(chunks, start=1):
            chunk_file = chunk_dir / f"{chunk_index:04d}.{ext}"
            result.chunks_total += 1
            if resume and chunk_file.exists() and chunk_file.stat().st_size > 0:
                result.chunks_reused += 1
            else:
                engine.synthesize(chunk, chunk_file)
                log(f"    chunk {chunk_index}/{len(chunks)} done")
            chunk_files.append(chunk_file)

        audio.concat_audio(chunk_files, chapter_file)
        result.chapter_files.append(chapter_file)

    if make_m4b:
        book_file = out_dir / f"{_safe_filename(book_title)}.m4b"
        log(f"Building audiobook file: {book_file.name}")
        audio.make_m4b(
            result.chapter_files,
            [c.title for c in chapters],
            book_file,
            title=book_title,
            author=author,
        )
        result.book_file = book_file
    elif single_file:
        book_file = out_dir / f"{_safe_filename(book_title)}.{ext}"
        log(f"Combining into: {book_file.name}")
        audio.concat_audio(result.chapter_files, book_file)
        result.book_file = book_file

    result.seconds_elapsed = time.monotonic() - started
    return result


def _title_from_input(input_path: Path, chapters: list[Chapter]) -> str:
    if input_path.is_dir():
        return input_path.name.replace("_", " ").strip() or "Audiobook"
    stem = input_path.stem.replace("_", " ").strip()
    if stem:
        return stem
    return chapters[0].title if chapters else "Audiobook"
