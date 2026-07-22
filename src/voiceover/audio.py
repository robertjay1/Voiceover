"""Audio assembly: concatenating chunks, encoding, and m4b chaptering.

Uses ffmpeg when available (recommended). Without ffmpeg there are pure-
Python fallbacks for concatenation (WAV via the wave module; MP3 by frame
concatenation, which players handle fine), but m4b and format conversion
require ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path


class AudioError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AudioError(
            f"{cmd[0]} failed (exit {result.returncode}): {result.stderr.strip()[-800:]}"
        )


def _concat_list_file(files: list[Path], list_path: Path) -> None:
    # ffmpeg concat demuxer escaping: wrap in single quotes, escape embedded ones.
    lines = "\n".join("file '{}'".format(str(f.resolve()).replace("'", r"'\''")) for f in files)
    list_path.write_text(lines + "\n", encoding="utf-8")


def _concat_wav_python(files: list[Path], out_path: Path) -> None:
    with wave.open(str(files[0]), "rb") as first:
        params = first.getparams()
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for file in files:
            with wave.open(str(file), "rb") as part:
                if part.getparams()[:3] != params[:3]:
                    raise AudioError(f"WAV format mismatch in {file}")
                out.writeframes(part.readframes(part.getnframes()))


def _concat_mp3_python(files: list[Path], out_path: Path) -> None:
    with open(out_path, "wb") as out:
        for file in files:
            out.write(file.read_bytes())


def concat_audio(files: list[Path], out_path: Path) -> None:
    """Concatenate same-format audio files into one."""
    if not files:
        raise AudioError("Nothing to concatenate.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(files) == 1:
        shutil.copyfile(files[0], out_path)
        return
    if ffmpeg_available():
        list_path = out_path.with_suffix(".txt")
        _concat_list_file(files, list_path)
        try:
            _run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(list_path),
                "-c", "copy", str(out_path),
            ])
        finally:
            list_path.unlink(missing_ok=True)
    elif out_path.suffix.lower() == ".wav":
        _concat_wav_python(files, out_path)
    else:
        _concat_mp3_python(files, out_path)


STD_FRAMERATE = 24000


def normalize_to_wav(in_path: Path, out_path: Path, framerate: int = STD_FRAMERATE) -> None:
    """Re-render any audio file as mono 16-bit WAV at a fixed sample rate.

    Multi-voice books mix engines whose native outputs differ (edge=mp3
    24 kHz, espeak=wav 22 kHz, piper varies); normalizing every chunk to
    one format makes concatenation seamless. Requires ffmpeg.
    """
    if not ffmpeg_available():
        raise AudioError("ffmpeg is required to mix voices from different engines.")
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(in_path), "-ar", str(framerate), "-ac", "1",
        "-sample_fmt", "s16", str(out_path),
    ])


def write_silence(path: Path, seconds: float, framerate: int = STD_FRAMERATE) -> None:
    """Write a mono 16-bit WAV of silence (pure Python, no ffmpeg)."""
    frames = max(1, int(seconds * framerate))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * frames)


def wav_framerate(path: Path) -> int:
    with wave.open(str(path), "rb") as w:
        return w.getframerate()


def convert(in_path: Path, out_path: Path, bitrate: str = "64k") -> None:
    """Convert between audio formats (e.g. wav -> mp3). Requires ffmpeg."""
    if not ffmpeg_available():
        raise AudioError("ffmpeg is required for format conversion. Install ffmpeg.")
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(in_path), "-b:a", bitrate, str(out_path),
    ])


def duration_seconds(path: Path) -> float:
    """Length of an audio file in seconds."""
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    if shutil.which("ffprobe") is None:
        raise AudioError("ffprobe is required to measure non-WAV durations.")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise AudioError(f"Could not read duration of {path}: {result.stderr.strip()}") from exc


def _ffmetadata_escape(value: str) -> str:
    for char in "\\=;#\n":
        value = value.replace(char, "\\" + char)
    return value


def make_m4b(
    chapter_files: list[Path],
    chapter_titles: list[str],
    out_path: Path,
    title: str,
    author: str | None = None,
    bitrate: str = "64k",
) -> None:
    """Build a single .m4b audiobook with embedded chapter markers."""
    if not ffmpeg_available():
        raise AudioError("ffmpeg is required to create .m4b audiobooks. Install ffmpeg.")

    metadata = ";FFMETADATA1\n"
    metadata += f"title={_ffmetadata_escape(title)}\n"
    if author:
        metadata += f"artist={_ffmetadata_escape(author)}\n"
    metadata += "genre=Audiobook\n"

    start_ms = 0
    for file, chapter_title in zip(chapter_files, chapter_titles):
        end_ms = start_ms + round(duration_seconds(file) * 1000)
        metadata += (
            "[CHAPTER]\nTIMEBASE=1/1000\n"
            f"START={start_ms}\nEND={end_ms}\n"
            f"title={_ffmetadata_escape(chapter_title)}\n"
        )
        start_ms = end_ms

    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = out_path.with_suffix(".ffmeta")
    list_path = out_path.with_suffix(".txt")
    meta_path.write_text(metadata, encoding="utf-8")
    _concat_list_file(chapter_files, list_path)
    try:
        _run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-i", str(meta_path), "-map_metadata", "1",
            "-map", "0:a", "-c:a", "aac", "-b:a", bitrate,
            "-movflags", "+faststart", str(out_path),
        ])
    finally:
        meta_path.unlink(missing_ok=True)
        list_path.unlink(missing_ok=True)
