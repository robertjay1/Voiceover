"""The audiobook build pipeline: chapters -> chunks -> audio -> book."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import audio
from .chapters import Chapter, load_chapters
from .chunking import chunk_text
from .dialogue import segment_dialogue
from .engines.base import EngineError, TTSEngine
from .voicebank import Cast, VoiceProfile


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


class _EnginePool:
    """Lazily creates and caches one engine instance per voice profile."""

    def __init__(self) -> None:
        self._engines: dict[str, TTSEngine] = {}

    def get(self, profile: VoiceProfile) -> TTSEngine:
        key = profile.key()
        if key not in self._engines:
            self._engines[key] = profile.create()
        return self._engines[key]


def _render_chapter_multivoice(
    chapter: Chapter,
    chunk_dir: Path,
    chapter_file: Path,
    cast: Cast,
    engines: _EnginePool,
    *,
    turn_gap: float,
    max_chunk_chars: int,
    resume: bool,
    result: BuildResult,
    lexicon,
    log,
) -> None:
    """Render one chapter with a different voice per speaker.

    Every chunk is normalized to a common WAV format so voices from
    different engines join seamlessly, with a short silence between
    speaker turns for natural pacing.
    """
    from .engines import CHUNK_LIMITS

    segments = segment_dialogue(chapter.text)
    units: list[tuple[VoiceProfile, str]] = []
    for segment in segments:
        profile = cast.profile_for(segment.speaker)
        limit = CHUNK_LIMITS.get(profile.engine)
        effective = min(max_chunk_chars, limit) if limit else max_chunk_chars
        for chunk in chunk_text(segment.text, effective):
            units.append((profile, lexicon.apply(chunk) if lexicon else chunk))

    speakers = sorted({s.speaker for s in segments if s.is_dialogue})
    if speakers:
        log(f"    speakers: {', '.join(speakers)}")

    use_ffmpeg = audio.ffmpeg_available()
    chunk_files: list[Path] = []
    framerate: int | None = audio.STD_FRAMERATE if use_ffmpeg else None

    for unit_index, (profile, chunk) in enumerate(units, start=1):
        digest = hashlib.sha1(chunk.encode("utf-8")).hexdigest()[:8]
        chunk_file = chunk_dir / f"{unit_index:04d}-{profile.key()[:40]}-{digest}.wav"
        result.chunks_total += 1
        if resume and chunk_file.exists() and chunk_file.stat().st_size > 0:
            result.chunks_reused += 1
        else:
            engine = engines.get(profile)
            if use_ffmpeg:
                native = chunk_file.with_suffix(f".native.{engine.extension}")
                engine.synthesize(chunk, native)
                audio.normalize_to_wav(native, chunk_file)
                native.unlink(missing_ok=True)
            else:
                if engine.extension != "wav":
                    raise EngineError(
                        "Mixing voices with the "
                        f"'{profile.engine}' engine requires ffmpeg. Install ffmpeg."
                    )
                engine.synthesize(chunk, chunk_file)
            log(f"    chunk {unit_index}/{len(units)} done")
        if framerate is None:
            framerate = audio.wav_framerate(chunk_file)
        chunk_files.append(chunk_file)

    # Short breath between speaker turns. A dialogue tag ("said Ray.")
    # belongs to the line it accompanies, so a gap on both sides of it
    # chops the flow — suppress the gap adjacent to short narrator tags
    # and use a briefer one there.
    gap_file = chunk_dir / f"_gap-{framerate}.wav"
    tag_gap_file = chunk_dir / f"_gap-tag-{framerate}.wav"
    if turn_gap > 0 and not gap_file.exists():
        audio.write_silence(gap_file, turn_gap, framerate)
        audio.write_silence(tag_gap_file, min(turn_gap, 0.12), framerate)

    def _is_short_tag(profile: VoiceProfile, text: str) -> bool:
        return profile.key() == narrator_key and len(text.split()) <= 4

    narrator_key = cast.narrator_profile.key()
    sequence: list[Path] = []
    prev_profile: VoiceProfile | None = None
    prev_text: str = ""
    for (profile, text), chunk_file in zip(units, chunk_files):
        if turn_gap > 0 and prev_profile is not None and profile.key() != prev_profile.key():
            # No full turn-gap around a short dialogue tag — just a beat.
            if _is_short_tag(profile, text) or _is_short_tag(prev_profile, prev_text):
                sequence.append(tag_gap_file)
            else:
                sequence.append(gap_file)
        sequence.append(chunk_file)
        prev_profile, prev_text = profile, text

    if use_ffmpeg:
        chapter_wav = chunk_dir / "_chapter.wav"
        audio.concat_audio(sequence, chapter_wav)
        audio.convert(chapter_wav, chapter_file, bitrate="96k")
        chapter_wav.unlink(missing_ok=True)
    else:
        audio.concat_audio(sequence, chapter_file)


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
    cast: Cast | None = None,
    turn_gap: float = 0.3,
    lexicon=None,
    log=print,
) -> BuildResult:
    """Render input text into per-chapter audio files, optionally combined.

    Chunk audio is cached in <out_dir>/.chunks/; re-running after a crash
    or interruption reuses every finished chunk (resume=True).

    With a cast, dialogue is detected and each speaker gets their own
    voice; narration uses the narrator profile.
    """
    started = time.monotonic()
    input_path = Path(input_path)
    out_dir = Path(out_dir)
    chapters = load_chapters(input_path)
    if not chapters:
        raise ValueError(f"No readable text found in {input_path}")

    book_title = title or _title_from_input(input_path, chapters)
    multivoice = cast is not None
    if multivoice:
        ext = "mp3" if audio.ffmpeg_available() else "wav"
    else:
        ext = engine.extension
    work_dir = out_dir / ".chunks"
    result = BuildResult()
    engines = _EnginePool()

    total_words = sum(c.words for c in chapters)
    log(f"Narrating: {book_title}")
    log(f"Engine:    {engine.describe()}" + ("  [multi-voice]" if multivoice else ""))
    log(f"Chapters:  {len(chapters)}  ({total_words:,} words)")

    for index, chapter in enumerate(chapters, start=1):
        chapter_stem = f"{index:02d} - {_safe_filename(chapter.title)}"
        chapter_file = out_dir / f"{chapter_stem}.{ext}"
        chunk_dir = work_dir / f"ch{index:03d}"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        if multivoice:
            log(f"[{index}/{len(chapters)}] {chapter.title}")
            _render_chapter_multivoice(
                chapter, chunk_dir, chapter_file, cast, engines,
                turn_gap=turn_gap, max_chunk_chars=max_chunk_chars,
                resume=resume, result=result, lexicon=lexicon, log=log,
            )
            result.chapter_files.append(chapter_file)
            continue

        engine_limit = getattr(engine, "preferred_chunk_chars", None)
        effective_chars = min(max_chunk_chars, engine_limit) if engine_limit else max_chunk_chars
        chunks = chunk_text(chapter.text, effective_chars)
        if lexicon:
            chunks = [lexicon.apply(c) for c in chunks]
        log(f"[{index}/{len(chapters)}] {chapter.title} — {len(chunks)} chunk(s)")

        chunk_files: list[Path] = []
        for chunk_index, chunk in enumerate(chunks, start=1):
            digest = hashlib.sha1(chunk.encode("utf-8")).hexdigest()[:8]
            chunk_file = chunk_dir / f"{chunk_index:04d}-{digest}.{ext}"
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
    if input_path.suffix.lower() == ".epub":
        from .epub import book_title

        title = book_title(input_path)
        if title:
            return title
    if input_path.is_dir():
        return input_path.name.replace("_", " ").strip() or "Audiobook"
    stem = input_path.stem.replace("_", " ").strip()
    if stem:
        return stem
    return chapters[0].title if chapters else "Audiobook"
