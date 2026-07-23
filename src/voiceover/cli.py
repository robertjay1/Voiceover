"""Command-line interface for Voiceover."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import json

from . import __version__
from .audio import AudioError, ffmpeg_available
from .book import build_audiobook
from .chapters import load_chapters
from .chunking import chunk_text
from .dialogue import NARRATOR, speaker_stats
from .engines import ENGINE_NAMES
from .engines.base import EngineError
from .voicebank import (
    AUTO_POOLS,
    Cast,
    VoiceProfile,
    load_bank,
    save_bank,
)


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s" if hours else f"{minutes}m {secs:02d}s"


def _narrator_profile(args: argparse.Namespace) -> VoiceProfile:
    from .voicebank import DEFAULT_VOICES

    # --voice may name a saved voice-bank profile; the profile then
    # defines the whole narrator setup (engine, voice, rate, volume).
    if args.voice:
        bank_path = getattr(args, "bank", None)
        bank = load_bank(bank_path, required=bank_path is not None)
        if args.voice in bank:
            return bank[args.voice]
    return VoiceProfile(
        engine=args.engine,
        voice=args.voice or DEFAULT_VOICES.get(args.engine),
        rate=args.rate,
        volume=getattr(args, "volume", 1.0),
        model_dir=getattr(args, "model_dir", None),
        pitch=getattr(args, "pitch", 1.0),
    )


def _load_cast(args: argparse.Namespace) -> Cast | None:
    cast_path = getattr(args, "cast", None)
    if not cast_path and not getattr(args, "multi_voice", False):
        return None
    bank_path = getattr(args, "bank", None)
    bank = load_bank(bank_path, required=bank_path is not None)
    narrator = _narrator_profile(args)
    cast = Cast.load(
        Path(cast_path) if cast_path else None,
        bank,
        default_engine=args.engine,
        narrator_profile=narrator,
    )
    # A cast entry may rename the narrator voice too.
    if "narrator" in cast.mapping:
        cast.narrator_profile = cast.mapping["narrator"]
    return cast


def cmd_build(args: argparse.Namespace) -> int:
    if (args.m4b or args.single) and not ffmpeg_available() and args.m4b:
        print("error: creating .m4b requires ffmpeg — install it first.", file=sys.stderr)
        return 2

    cast = _load_cast(args)
    engine = (cast.narrator_profile if cast else _narrator_profile(args)).create()
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
        cast=cast,
        turn_gap=args.turn_gap,
    )

    print()
    reused = f" ({result.chunks_reused} reused from previous run)" if result.chunks_reused else ""
    print(f"Done in {_format_duration(result.seconds_elapsed)} — "
          f"{result.chunks_total} chunk(s){reused}.")
    for chapter_file in result.chapter_files:
        print(f"  {chapter_file}")
    if result.book_file:
        print(f"  {result.book_file}  <- complete audiobook")
    if cast:
        print("\nCast used:")
        width = max(len(s) for s in list(cast.assignments()) + ["narrator"])
        print(f"  {'narrator':{width}s}  {cast.narrator_profile.label()}")
        for speaker, profile in sorted(cast.assignments().items()):
            if speaker != "narrator":
                print(f"  {speaker:{width}s}  {profile.label()}")
    return 0


def cmd_cast(args: argparse.Namespace) -> int:
    """Analyze speakers and write an editable cast file template."""
    chapters = load_chapters(Path(args.input))
    counts: dict[str, int] = {}
    for chapter in chapters:
        for speaker, words in speaker_stats(chapter.text).items():
            counts[speaker] = counts.get(speaker, 0) + words

    dialogue_speakers = {s: w for s, w in counts.items() if s != NARRATOR}
    ranked = sorted(dialogue_speakers.items(), key=lambda kv: -kv[1])

    print(f"Detected {len(ranked)} speaker(s) plus the narrator:\n")
    narrator_words = counts.get(NARRATOR, 0)
    print(f"  {'narrator':24s} {narrator_words:8,d} words")
    for speaker, words in ranked:
        print(f"  {speaker:24s} {words:8,d} words")

    from .voicebank import DEFAULT_VOICES

    pool = AUTO_POOLS.get(args.engine, [])
    cast_data: dict = {}
    narrator_voice = DEFAULT_VOICES.get(args.engine, "")
    cast_data["narrator"] = narrator_voice
    available = [v for v in pool if v != narrator_voice]
    for index, (speaker, _words) in enumerate(ranked):
        cast_data[speaker] = available[index % len(available)] if available else ""

    out_path = Path(args.out)
    out_path.write_text(json.dumps(cast_data, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote cast template: {out_path}")
    print("Edit the voice for each speaker (bank profile names work too), then run:")
    print(f"  voiceover build {args.input} --cast {out_path}")
    return 0


def cmd_clone(args: argparse.Namespace) -> int:
    """Create a cloned voice from a reference recording and save it to the bank."""
    sample = Path(args.sample).expanduser().resolve()
    if not sample.is_file():
        print(f"error: sample recording not found: {sample}", file=sys.stderr)
        return 1

    if sample.suffix.lower() == ".wav":
        import wave

        try:
            with wave.open(str(sample), "rb") as w:
                seconds = w.getnframes() / w.getframerate()
            if seconds < 5:
                print(f"note: sample is only {seconds:.1f}s — 10–20s of clean "
                      "speech clones noticeably better.")
            elif seconds > 40:
                print(f"note: sample is {seconds:.0f}s — chatterbox only uses "
                      "the first portion; 10–20s is ideal.")
        except wave.Error:
            pass

    bank_path = args.bank
    bank = load_bank(bank_path)
    bank[args.name] = VoiceProfile(
        engine="chatterbox",
        sample=str(sample),
        exaggeration=args.exaggeration,
    )
    path = save_bank(bank, bank_path)
    print(f"Saved cloned voice '{args.name}' (from {sample.name}) to {path}")
    print("\nOnly clone voices you have the right to use — your own, or a "
          "speaker who gave permission.\nTry it:")
    print(f"  voiceover preview \"This is my cloned voice.\" --voice {args.name}")
    print(f"  voiceover build book.md --voice {args.name} --m4b")
    return 0


def cmd_bank(args: argparse.Namespace) -> int:
    bank_path = args.bank
    bank = load_bank(bank_path)

    if args.bank_command == "list":
        if not bank:
            print("Voice bank is empty. Add one with:\n"
                  "  voiceover bank add my-narrator --engine edge "
                  "--voice en-US-AndrewMultilingualNeural --rate 1.0")
            return 0
        width = max(len(name) for name in bank)
        for name, profile in sorted(bank.items()):
            print(f"  {name:{width}s}  {profile.label()}")
        return 0

    if args.bank_command == "add":
        if not args.voice and not args.sample:
            print("error: provide --voice, or --sample for a cloned voice.", file=sys.stderr)
            return 2
        bank[args.name] = VoiceProfile(
            engine=args.engine,
            voice=args.voice,
            rate=args.rate,
            volume=args.volume,
            model_dir=args.model_dir,
            sample=str(Path(args.sample).expanduser().resolve()) if args.sample else None,
            pitch=args.pitch,
        )
        path = save_bank(bank, bank_path)
        print(f"Saved '{args.name}' ({bank[args.name].label()}) to {path}")
        return 0

    if args.bank_command == "remove":
        if args.name not in bank:
            print(f"error: no profile named '{args.name}' in the bank.", file=sys.stderr)
            return 1
        del bank[args.name]
        path = save_bank(bank, bank_path)
        print(f"Removed '{args.name}' from {path}")
        return 0

    return 2


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
    elif args.engine == "kokoro":
        from .engines.kokoro import KNOWN_VOICES

        for voice in KNOWN_VOICES:
            print(f"  {voice}")
        print("\nPrefix key: a=American, b=British; f=female, m=male.")
        print("Blend voices into your own with weights, e.g.:")
        print('  --engine kokoro --voice "af_heart*0.6+af_sky*0.4"')
    elif args.engine == "chatterbox":
        print("Chatterbox voices are cloned from a reference recording:\n"
              "  voiceover clone my-voice --sample me.wav\n"
              "Without a sample it uses its built-in voice. Only clone voices\n"
              "you have the right to use.")
    else:
        print("Piper voices are .onnx models you download once, e.g.:\n"
              "  python -m piper.download_voices en_US-lessac-medium --data-dir ./voices\n"
              "Browse samples at https://rhasspy.github.io/piper-samples/\n"
              "Then: voiceover build ... --engine piper --voice en_US-lessac-medium "
              "--model-dir ./voices")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    engine = _narrator_profile(args).create()
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
        p.add_argument("--pitch", type=float, default=1.0,
                       help="pitch multiplier, e.g. 1.1 higher / 0.9 lower (edge only)")
        p.add_argument("--model-dir", default=None,
                       help="directory containing Piper .onnx voice models")
        p.add_argument("--bank", default=None,
                       help="voice bank file (default: ~/.voiceover/voicebank.json)")

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
    p_build.add_argument("--cast", help="JSON cast file mapping speakers to voices "
                                        "(see 'voiceover cast') — enables multi-voice")
    p_build.add_argument("--multi-voice", action="store_true",
                         help="detect dialogue and auto-assign a distinct voice per speaker")
    p_build.add_argument("--turn-gap", type=float, default=0.35,
                         help="silence in seconds between speaker turns (default: 0.35)")
    add_engine_args(p_build)
    p_build.set_defaults(func=cmd_build)

    p_cast = sub.add_parser(
        "cast", help="detect speakers in a book and write a cast file to edit"
    )
    p_cast.add_argument("input", help="text/markdown file, or directory of chapter files")
    p_cast.add_argument("-o", "--out", default="cast.json", help="cast file to write")
    p_cast.add_argument("--engine", choices=ENGINE_NAMES, default="edge")
    p_cast.set_defaults(func=cmd_cast)

    p_clone = sub.add_parser(
        "clone",
        help="clone a voice from a recording (saved to your voice bank)",
        description="Clone a voice from ~10-20 seconds of clean speech and "
                    "save it as a named bank profile. Uses the chatterbox "
                    "engine (pip install voiceover[clone]). Only clone voices "
                    "you have the right to use.",
    )
    p_clone.add_argument("name", help="bank profile name for the cloned voice")
    p_clone.add_argument("--sample", required=True,
                         help="reference recording (wav/mp3/flac, ~10-20s of clean speech)")
    p_clone.add_argument("--exaggeration", type=float, default=None,
                         help="expressiveness 0..1 (default: engine's neutral 0.5)")
    p_clone.add_argument("--bank", default=None,
                         help="voice bank file (default: ~/.voiceover/voicebank.json)")
    p_clone.set_defaults(func=cmd_clone)

    p_bank = sub.add_parser("bank", help="manage your bank of reusable named voices")
    p_bank.add_argument("--bank", default=None,
                        help="voice bank file (default: ~/.voiceover/voicebank.json)")
    bank_sub = p_bank.add_subparsers(dest="bank_command", required=True)
    b_list = bank_sub.add_parser("list", help="show saved voice profiles")
    b_list.set_defaults(func=cmd_bank)
    b_add = bank_sub.add_parser("add", help="save a named voice profile")
    b_add.add_argument("name", help="profile name, e.g. gruff-captain")
    b_add.add_argument("--engine", choices=ENGINE_NAMES, default="edge")
    b_add.add_argument("--voice", help="engine voice name, piper model, or kokoro blend")
    b_add.add_argument("--rate", type=float, default=1.0)
    b_add.add_argument("--volume", type=float, default=1.0)
    b_add.add_argument("--model-dir", default=None, help="piper model directory")
    b_add.add_argument("--sample", default=None,
                       help="reference recording for a cloned (chatterbox) voice")
    b_add.add_argument("--pitch", type=float, default=1.0,
                       help="pitch multiplier (edge engine only)")
    b_add.set_defaults(func=cmd_bank)
    b_remove = bank_sub.add_parser("remove", help="delete a voice profile")
    b_remove.add_argument("name")
    b_remove.set_defaults(func=cmd_bank)

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
    except BrokenPipeError:
        # Output piped into head/less that closed early — not an error.
        return 0


if __name__ == "__main__":
    sys.exit(main())
