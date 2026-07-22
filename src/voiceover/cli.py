"""Command-line interface for Voiceover."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .audio import AudioError, ffmpeg_available
from .book import build_audiobook
from .chapters import load_chapters
from .chunking import chunk_text
from .engines import ENGINE_NAMES, create_engine
from .engines.base import EngineError


def _engine_options(args: argparse.Namespace) -> dict:
    options: dict = {"voice": args.voice, "rate": args.rate}
    if args.engine == "edge":
        options["volume"] = args.volume
    if args.engine == "piper":
        options["model_dir"] = args.model_dir
    return options


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s" if hours else f"{minutes}m {secs:02d}s"


def cmd_build(args: argparse.Namespace) -> int:
    if (args.m4b or args.single) and not ffmpeg_available() and args.m4b:
        print("error: creating .m4b requires ffmpeg — install it first.", file=sys.stderr)
        return 2

    engine = create_engine(args.engine, **_engine_options(args))
    result = build_audiobook(
        Path(args.input),
        Path(args.out),
        engine,
        title=args.title,
        author=args.author,
        make_m4b=args.m4b,
        single_file=args.single,
        max_chunk_chars=args.max_chunk_chars,
        resume=not args.no_resume,
    )

    print()
    reused = f" ({result.chunks_reused} reused from previous run)" if result.chunks_reused else ""
    print(f"Done in {_format_duration(result.seconds_elapsed)} — "
          f"{result.chunks_total} chunk(s){reused}.")
    for chapter_file in result.chapter_files:
        print(f"  {chapter_file}")
    if result.book_file:
        print(f"  {result.book_file}  <- complete audiobook")
    return 0


def cmd_chapters(args: argparse.Namespace) -> int:
    chapters = load_chapters(Path(args.input))
    total_words = sum(c.words for c in chapters)
    print(f"{len(chapters)} chapter(s), {total_words:,} words "
          f"(~{_format_duration(total_words / 150 * 60)} narration at 150 wpm)\n")
    for index, chapter in enumerate(chapters, start=1):
        chunk_count = len(chunk_text(chapter.text))
        print(f"{index:3d}. {chapter.title}  — {chapter.words:,} words, {chunk_count} chunk(s)")
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    if args.engine == "edge":
        from .engines.edge import list_voices

        voices = list_voices(args.language)
        for voice in voices:
            print(f"{voice['ShortName']:40s} {voice['Gender']:8s} {voice['Locale']}")
        print(f"\n{len(voices)} voice(s). Use with: voiceover build ... --voice <ShortName>")
    elif args.engine == "espeak":
        from .engines.espeak import list_voices

        print(list_voices(args.language))
    else:
        print("Piper voices are .onnx models you download once, e.g.:\n"
              "  python -m piper.download_voices en_US-lessac-medium --data-dir ./voices\n"
              "Browse samples at https://rhasspy.github.io/piper-samples/\n"
              "Then: voiceover build ... --engine piper --voice en_US-lessac-medium "
              "--model-dir ./voices")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    engine = create_engine(args.engine, **_engine_options(args))
    out_path = Path(args.out) if args.out else Path(f"preview.{engine.extension}")
    engine.synthesize(args.text, out_path)
    print(f"Wrote {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voiceover",
        description="Generate audiobooks and long-form narration from text/markdown.",
    )
    parser.add_argument("--version", action="version", version=f"voiceover {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_engine_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--engine", choices=ENGINE_NAMES, default="edge",
                       help="TTS engine (default: edge — free online neural voices)")
        p.add_argument("--voice", help="voice name (see 'voiceover voices')")
        p.add_argument("--rate", type=float, default=1.0,
                       help="speaking speed multiplier, e.g. 1.2 (default: 1.0)")
        p.add_argument("--volume", type=float, default=1.0,
                       help="volume multiplier (edge engine only)")
        p.add_argument("--model-dir", default=None,
                       help="directory containing Piper .onnx voice models")

    p_build = sub.add_parser("build", help="narrate a book/text into audio files")
    p_build.add_argument("input", help="text/markdown file, or directory of chapter files")
    p_build.add_argument("-o", "--out", default="audiobook", help="output directory")
    p_build.add_argument("--title", help="book title (default: from input filename)")
    p_build.add_argument("--author", help="author name (embedded in m4b metadata)")
    p_build.add_argument("--m4b", action="store_true",
                         help="also produce a single .m4b audiobook with chapter markers")
    p_build.add_argument("--single", action="store_true",
                         help="also combine chapters into one audio file")
    p_build.add_argument("--max-chunk-chars", type=int, default=1800,
                         help="max characters per synthesis chunk (default: 1800)")
    p_build.add_argument("--no-resume", action="store_true",
                         help="re-synthesize everything, ignoring cached chunks")
    add_engine_args(p_build)
    p_build.set_defaults(func=cmd_build)

    p_chapters = sub.add_parser("chapters", help="preview chapter detection without synthesizing")
    p_chapters.add_argument("input", help="text/markdown file, or directory of chapter files")
    p_chapters.set_defaults(func=cmd_chapters)

    p_voices = sub.add_parser("voices", help="list available voices")
    p_voices.add_argument("--engine", choices=ENGINE_NAMES, default="edge")
    p_voices.add_argument("-l", "--language", help="filter by language/locale, e.g. en or en-GB")
    p_voices.set_defaults(func=cmd_voices)

    p_preview = sub.add_parser("preview", help="synthesize a short text to try out a voice")
    p_preview.add_argument("text", help="text to speak")
    p_preview.add_argument("-o", "--out", help="output file (default: preview.<ext>)")
    add_engine_args(p_preview)
    p_preview.set_defaults(func=cmd_preview)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (EngineError, AudioError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted — progress is saved; re-run the same command to resume.",
              file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
