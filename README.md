# 🔊 Voiceover

Turn books and long-form text into audiobooks. Voiceover is a command-line
tool that takes text or markdown files, detects chapters, narrates them with
natural-sounding neural voices, and produces per-chapter MP3s or a single
`.m4b` audiobook with embedded chapter markers — ready for any audiobook
player.

```
$ voiceover build mybook.md -o audiobook --m4b --author "Jane Doe"
Narrating: mybook
Engine:    edge (en-US-AriaNeural, rate +0%)
Chapters:  14  (86,300 words)
[1/14] The Beginning — 18 chunk(s)
...
  audiobook/01 - The Beginning.mp3
  ...
  audiobook/mybook.m4b  <- complete audiobook
```

## Features

- **Multi-voice narration** — detects who's speaking in dialogue and gives
  every character their own voice, with the narrator reading the prose.
  Handles attribution that only arrives after the quote (`"Run," said Mira.`),
  bare pronoun tags (`he said` — resolved from surrounding narration),
  interrupted quotes, and unattributed alternating exchanges.
- **Voice bank** — build a personal library of named, reusable voice
  profiles (`gruff-captain`, `warm-narrator`…) and cast them in any book.
- **Chapter detection** — markdown headings (`#`, `##`), plain-text openers
  (`Chapter 7`, `PART II`, `Prologue`…), or one-file-per-chapter directories.
- **Voice cloning** — clone a voice from ~10 seconds of recorded speech and
  narrate whole books with it, entirely on your own machine.
- **Five TTS engines**:
  | Engine | Quality | Internet | Notes |
  |---|---|---|---|
  | `edge` (default) | ★★★★★ neural | required | Free Microsoft neural voices, 90+ languages, no API key |
  | `kokoro` | ★★★★★ neural | offline¹ | Runs on CPU in real time; blendable voices (Apache-2.0) |
  | `chatterbox` | ★★★★★ cloned | offline¹ | Zero-shot voice cloning from a short sample (MIT) |
  | `piper` | ★★★★ neural | offline¹ | Local ONNX models, lightweight |
  | `espeak` | ★ robotic | offline | Instant — for previews and testing |

  ¹ one-time model download, then fully offline.
- **Resume** — synthesis is chunked and cached; an interrupted 8-hour render
  picks up where it left off instead of starting over.
- **`.m4b` audiobooks** with chapter markers, title/author metadata (via ffmpeg).
- **Markdown-aware narration** — strips link URLs, emphasis markers, code
  fences, and bullets so the narrator doesn't read syntax aloud.
- **Speed control** (`--rate 1.2`), per-language voice pick, dry-run chapter
  preview.

## Install

```sh
pip install ./                # from a clone of this repo
# recommended: ffmpeg for m4b/mp3 assembly
#   Linux: apt install ffmpeg     macOS: brew install ffmpeg
```

Optional engines:

```sh
pip install piper-tts         # offline neural voices
apt install espeak-ng         # instant preview voice (brew install espeak-ng on macOS)
```

## Usage

**1. Check how your book will be split** (no audio generated):

```sh
voiceover chapters mybook.md
```

**2. Pick a voice:**

```sh
voiceover voices -l en                # list English edge voices
voiceover preview "How does this voice sound?" --voice en-GB-RyanNeural
```

**3. Build the audiobook:**

```sh
voiceover build mybook.md -o audiobook --voice en-GB-RyanNeural --m4b --author "Jane Doe"
```

You get one MP3 per chapter plus `mybook.m4b` — a single audiobook file with
chapter navigation that works in Apple Books, Audiobookshelf, Plex, and most
audiobook apps.

## Multi-voice narration (character voices)

Give each character in your book their own voice. First see who Voiceover
detects:

```sh
voiceover cast mybook.md -o cast.json
```

```
Detected 2 speaker(s) plus the narrator:

  narrator          14,203 words
  Mira               1,882 words
  Elias              1,540 words

Wrote cast template: cast.json
```

Edit `cast.json` to taste — values can be an engine voice name, a voice-bank
profile, or an inline setting; map two aliases of the same character to one
voice:

```json
{
  "narrator": "en-US-AndrewMultilingualNeural",
  "Elias": "gruff-keeper",
  "the old man": "gruff-keeper",
  "Mira": { "voice": "en-US-EmmaMultilingualNeural", "rate": 1.05 }
}
```

Then build with the cast:

```sh
voiceover build mybook.md --cast cast.json --m4b
```

Or skip the cast file entirely and let Voiceover auto-assign distinct voices:

```sh
voiceover build mybook.md --multi-voice --m4b
```

How attribution works: explicit tags are matched before and *after* each
quote (`"Run," said Mira.`), a named tag anywhere in a paragraph claims its
other quotes, bare pronoun tags (`he said`) are resolved from characters
recently mentioned in the narration, and unattributed lines in a two-person
exchange alternate. Anything genuinely ambiguous stays with the narrator —
the same behavior as a single-voice audiobook. Speakers not listed in the
cast are auto-assigned distinct voices deterministically. A short
configurable silence (`--turn-gap`, default 0.35 s) is inserted between
speaker turns for natural pacing. Multi-voice mode works best with ffmpeg
installed (required when mixing engines or using edge voices).

## The voice bank — your own stock of voices

Save voices you like — engine, voice, and speed — under memorable names,
once, and reuse them across every project:

```sh
voiceover bank add warm-narrator --voice en-US-AndrewMultilingualNeural --rate 0.98
voiceover bank add gruff-keeper  --voice en-GB-RyanNeural --rate 0.9
voiceover bank add young-woman   --voice en-US-EmmaMultilingualNeural --rate 1.05
voiceover bank list
```

The bank lives in `~/.voiceover/voicebank.json` (override with `--bank`).
Bank names work anywhere a voice is accepted — in cast files and directly
as `--voice`:

```sh
voiceover build mybook.md --voice warm-narrator --m4b
voiceover preview "Testing my saved voice." --voice gruff-keeper
```

Profiles can use different engines — an edge narrator can share a book
with piper characters (ffmpeg required to mix).

### Input formats

- **Markdown file** — `#`/`##` headings become chapters; deeper headings stay
  inside their chapter.
- **Plain-text file** — lines like `Chapter 3`, `PART II: Exile`, `Epilogue`
  become chapter breaks; if none are found, the whole file is one chapter.
- **Directory** — each `.txt`/`.md` file becomes a chapter, in filename order
  (`01_intro.md`, `02_departure.md`, …).

## Clone your own voice

Record 10–20 seconds of clean speech (no music, minimal room echo), then:

```sh
pip install "voiceover[clone]"          # Chatterbox: local, MIT-licensed
voiceover clone my-voice --sample me.wav
voiceover preview "This is my cloned voice." --voice my-voice
voiceover build book.md --voice my-voice --m4b
```

The clone is saved to your voice bank like any other profile, so it can be
the narrator, or cast as one character among many. Everything runs locally —
your recording never leaves your machine — and output carries Resemble's
imperceptible watermark, a responsible default for synthetic speech.
A GPU (CUDA or Apple Silicon) makes rendering fast; CPU works but is slow
for a full book. `--exaggeration 0.7` adds expressiveness.

**Only clone voices you have the right to use** — your own, or a speaker
who has given you permission.

## The most natural fully-offline narration: Kokoro

```sh
pip install "voiceover[kokoro]"         # ~330 MB model downloads on first use
voiceover voices --engine kokoro
voiceover build book.md --engine kokoro --voice af_heart --m4b
```

Kokoro is a small Apache-2.0 neural model that runs in real time on a
laptop CPU and sounds close to the cloud voices. It also supports **voice
blending** — mix voices with weights to design a signature voice of your
own, and save it to the bank:

```sh
voiceover bank add my-signature --engine kokoro --voice "af_heart*0.6+af_sky*0.4"
voiceover build book.md --voice my-signature --m4b
```

Multi-voice books work fully offline with kokoro too: uncast speakers are
auto-assigned from ten distinct kokoro voices
(`voiceover build book.md --engine kokoro --multi-voice`).

### Offline narration with Piper

```sh
pip install piper-tts
python -m piper.download_voices en_US-lessac-medium --data-dir ./voices
voiceover build mybook.md --engine piper --voice en_US-lessac-medium --model-dir ./voices --m4b
```

Browse voice samples at <https://rhasspy.github.io/piper-samples/>.

### Handy options

| Option | Meaning |
|---|---|
| `--rate 1.25` | narrate 25 % faster |
| `--single` | also merge all chapters into one file |
| `--no-resume` | ignore cached chunks and re-render everything |
| `--max-chunk-chars 1200` | smaller synthesis chunks |
| `--title` / `--author` | audiobook metadata |

Interrupted? Just re-run the same command — finished chunks are reused.

## Web demo

The `web/` folder contains a zero-dependency browser text-to-speech app
(Web Speech API): live word-highlighting, voice/rate/pitch controls, dark
mode. Open `web/index.html` in a browser, or serve the folder statically.
It plays text aloud but cannot export audio files — that's what the CLI
is for.

## Development

```sh
pip install -e .
python -m unittest discover -s tests
```

Project layout:

```
src/voiceover/
  cli.py         command-line interface
  chapters.py    chapter detection (markdown + plain text + directories)
  chunking.py    sentence-aware text chunking
  book.py        build pipeline (synthesis, caching/resume, assembly)
  audio.py       concat, conversion, m4b chaptering (ffmpeg + fallbacks)
  engines/       edge / piper / espeak backends
web/             browser TTS demo
tests/           unit tests (no network needed)
```

## Notes

- The `edge` engine uses Microsoft Edge's public read-aloud service. It's
  free and needs no key, but it is an online service — for guaranteed
  offline/private narration, or very large volumes, use `kokoro` or `piper`.
- Only narrate texts you have the rights to convert, and only clone voices
  you have the right to use.

## License

MIT
