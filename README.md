# 🔊 Voiceover

A free text-to-speech app that runs entirely in your browser. Type or paste any
text and hear it read aloud — no accounts, no server, and nothing is uploaded
anywhere. It uses the [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
built into modern browsers, so there are zero dependencies to install.

## Features

- **Voice picker** — choose from every voice installed on your system, grouped
  by language (Chrome also offers high-quality cloud voices).
- **Speed, pitch, and volume sliders** with live value readouts.
- **Read-along highlighting** — the word currently being spoken is highlighted
  and scrolled into view.
- **Pause / resume / stop** playback controls.
- **Long-text support** — text is split into sentence-sized chunks to work
  around browser limits on long utterances.
- **Saved preferences** — your voice and slider settings persist between visits
  (stored locally in your browser).
- **Keyboard shortcuts** — `Ctrl`/`⌘` + `Enter` to speak, `Esc` to stop.
- **Light & dark themes** following your system preference.

## Getting started

No build step is required. Either:

**Open directly** — double-click `index.html`, or

**Serve locally** (recommended, and required by some browsers for voices to load):

```sh
# any static server works, e.g.:
python3 -m http.server 8000
```

Then visit <http://localhost:8000>.

## Usage

1. Type or paste text into the box (or click **Sample text**).
2. Pick a voice and adjust speed, pitch, and volume to taste.
3. Press **Speak** — follow along with the live word highlighting.
4. Use **Pause**/**Resume** and **Stop** to control playback.

## Browser support

Works in any browser that implements the Web Speech API's speech synthesis:
Chrome, Edge, Safari (desktop and iOS), and Firefox. Available voices vary by
operating system and browser — Chrome typically offers the largest selection.

## Project structure

```
index.html   — page markup
styles.css   — styling (dark/light themes)
app.js       — speech logic, highlighting, settings persistence
```

## License

MIT
