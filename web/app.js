(() => {
  "use strict";

  const synth = window.speechSynthesis;

  const els = {
    unsupported: document.getElementById("unsupported"),
    app: document.querySelector(".app"),
    textInput: document.getElementById("text-input"),
    highlightView: document.getElementById("highlight-view"),
    charCount: document.getElementById("char-count"),
    sampleBtn: document.getElementById("sample-btn"),
    clearBtn: document.getElementById("clear-btn"),
    voiceSelect: document.getElementById("voice-select"),
    rate: document.getElementById("rate"),
    pitch: document.getElementById("pitch"),
    volume: document.getElementById("volume"),
    rateValue: document.getElementById("rate-value"),
    pitchValue: document.getElementById("pitch-value"),
    volumeValue: document.getElementById("volume-value"),
    resetBtn: document.getElementById("reset-btn"),
    speakBtn: document.getElementById("speak-btn"),
    pauseBtn: document.getElementById("pause-btn"),
    stopBtn: document.getElementById("stop-btn"),
    status: document.getElementById("status"),
  };

  if (!synth || !window.SpeechSynthesisUtterance) {
    els.app.hidden = true;
    els.unsupported.hidden = false;
    return;
  }

  const STORAGE_KEY = "voiceover-settings";
  const SAMPLE_TEXT =
    "Welcome to Voiceover! This is a small text-to-speech app that runs " +
    "entirely in your browser. Pick a voice, adjust the speed and pitch, " +
    "then press Speak. While it reads, each word is highlighted so you can " +
    "follow along.";

  // Some engines (notably Chrome's remote voices) silently stop on long
  // utterances, so text is split into sentence-sized chunks and queued.
  const MAX_CHUNK_LENGTH = 200;

  let voices = [];
  let speaking = false;
  let paused = false;
  // Offset of the currently speaking chunk within the full text, so word
  // boundary events (which are chunk-relative) can highlight the right word.
  let chunkOffset = 0;
  let queue = [];

  // ---------- Voices ----------

  function loadVoices() {
    voices = synth.getVoices();
    if (!voices.length) return;

    voices.sort((a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name));

    const saved = getSettings();
    els.voiceSelect.innerHTML = "";

    const groups = new Map();
    for (const voice of voices) {
      const langBase = voice.lang.split(/[-_]/)[0].toLowerCase();
      if (!groups.has(langBase)) {
        const group = document.createElement("optgroup");
        group.label = languageName(langBase) || voice.lang;
        groups.set(langBase, group);
        els.voiceSelect.appendChild(group);
      }
      const option = document.createElement("option");
      option.value = voice.voiceURI;
      option.textContent = `${voice.name} (${voice.lang})${voice.default ? " — default" : ""}`;
      groups.get(langBase).appendChild(option);
    }

    if (saved.voiceURI && voices.some((v) => v.voiceURI === saved.voiceURI)) {
      els.voiceSelect.value = saved.voiceURI;
    } else {
      const defaultVoice = voices.find((v) => v.default) || voices[0];
      els.voiceSelect.value = defaultVoice.voiceURI;
    }
  }

  function languageName(code) {
    try {
      return new Intl.DisplayNames(["en"], { type: "language" }).of(code);
    } catch {
      return null;
    }
  }

  function selectedVoice() {
    return voices.find((v) => v.voiceURI === els.voiceSelect.value) || null;
  }

  loadVoices();
  // Voices often load asynchronously (Chrome fires this after page load).
  synth.addEventListener("voiceschanged", loadVoices);

  // ---------- Settings persistence ----------

  function getSettings() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
      return {};
    }
  }

  function saveSettings() {
    const settings = {
      voiceURI: els.voiceSelect.value,
      rate: els.rate.value,
      pitch: els.pitch.value,
      volume: els.volume.value,
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* storage unavailable (private mode) — settings just won't persist */
    }
  }

  function applySettings(settings) {
    if (settings.rate) els.rate.value = settings.rate;
    if (settings.pitch) els.pitch.value = settings.pitch;
    if (settings.volume) els.volume.value = settings.volume;
    updateSliderLabels();
  }

  function updateSliderLabels() {
    els.rateValue.textContent = `${Number(els.rate.value).toFixed(1)}×`;
    els.pitchValue.textContent = Number(els.pitch.value).toFixed(1);
    els.volumeValue.textContent = `${Math.round(els.volume.value * 100)}%`;
  }

  applySettings(getSettings());

  // ---------- Text handling ----------

  function updateCharCount() {
    const count = els.textInput.value.length;
    els.charCount.textContent = `${count.toLocaleString()} character${count === 1 ? "" : "s"}`;
  }

  updateCharCount();

  function splitIntoChunks(text) {
    // Split on sentence boundaries, then merge tiny pieces and split any
    // oversized ones on the nearest space.
    const sentences = text.match(/[^.!?\n]+[.!?]*\s*|\n+/g) || [text];
    const chunks = [];
    let current = "";
    let offset = 0;

    const push = () => {
      if (current.trim()) chunks.push({ text: current, offset });
      offset += current.length;
      current = "";
    };

    for (const sentence of sentences) {
      if (current.length + sentence.length > MAX_CHUNK_LENGTH && current) push();
      if (sentence.length > MAX_CHUNK_LENGTH) {
        let rest = sentence;
        while (rest.length > MAX_CHUNK_LENGTH) {
          let cut = rest.lastIndexOf(" ", MAX_CHUNK_LENGTH);
          if (cut <= 0) cut = MAX_CHUNK_LENGTH;
          current = rest.slice(0, cut + 1);
          push();
          rest = rest.slice(cut + 1);
        }
        current = rest;
      } else {
        current += sentence;
      }
    }
    push();
    return chunks;
  }

  // ---------- Read-along highlighting ----------

  function showHighlightView(text) {
    els.highlightView.textContent = text;
    els.highlightView.hidden = false;
    els.textInput.hidden = true;
  }

  function hideHighlightView() {
    els.highlightView.hidden = true;
    els.textInput.hidden = false;
  }

  function highlightWord(globalIndex) {
    const text = els.textInput.value;
    let end = text.slice(globalIndex).search(/\s/);
    end = end === -1 ? text.length : globalIndex + end;

    const before = document.createTextNode(text.slice(0, globalIndex));
    const word = document.createElement("mark");
    word.className = "spoken-word";
    word.textContent = text.slice(globalIndex, end);
    const after = document.createTextNode(text.slice(end));

    els.highlightView.replaceChildren(before, word, after);
    word.scrollIntoView({ block: "nearest" });
  }

  // ---------- Playback ----------

  function setStatus(message, className = "") {
    els.status.textContent = message;
    els.status.className = `status ${className}`.trim();
  }

  function updateButtons() {
    els.speakBtn.disabled = speaking && !paused;
    els.pauseBtn.disabled = !speaking;
    els.stopBtn.disabled = !speaking;
    els.pauseBtn.innerHTML = paused
      ? '<span class="btn-icon" aria-hidden="true">▶</span> Resume'
      : '<span class="btn-icon" aria-hidden="true">⏸</span> Pause';
  }

  function speak() {
    if (speaking && paused) {
      synth.resume();
      paused = false;
      setStatus("Speaking…", "speaking");
      updateButtons();
      return;
    }

    const text = els.textInput.value;
    if (!text.trim()) {
      setStatus("Nothing to speak — type some text first.", "error");
      els.textInput.focus();
      return;
    }

    stop(true);
    queue = splitIntoChunks(text);
    if (!queue.length) return;

    speaking = true;
    paused = false;
    showHighlightView(text);
    setStatus("Speaking…", "speaking");
    updateButtons();
    speakNextChunk();
  }

  function speakNextChunk() {
    if (!queue.length) {
      finish();
      return;
    }

    const chunk = queue.shift();
    chunkOffset = chunk.offset;

    const utterance = new SpeechSynthesisUtterance(chunk.text);
    const voice = selectedVoice();
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    }
    utterance.rate = Number(els.rate.value);
    utterance.pitch = Number(els.pitch.value);
    utterance.volume = Number(els.volume.value);

    utterance.onboundary = (event) => {
      if (event.name === "word" || event.charIndex != null) {
        highlightWord(chunkOffset + event.charIndex);
      }
    };
    utterance.onend = () => {
      if (speaking) speakNextChunk();
    };
    utterance.onerror = (event) => {
      // "interrupted"/"canceled" are expected when the user presses Stop.
      if (event.error === "interrupted" || event.error === "canceled") return;
      finish();
      setStatus(`Speech error: ${event.error}`, "error");
    };

    synth.speak(utterance);
  }

  function pauseOrResume() {
    if (!speaking) return;
    if (paused) {
      synth.resume();
      paused = false;
      setStatus("Speaking…", "speaking");
    } else {
      synth.pause();
      paused = true;
      setStatus("Paused");
    }
    updateButtons();
  }

  function stop(silent = false) {
    queue = [];
    speaking = false;
    paused = false;
    synth.cancel();
    hideHighlightView();
    updateButtons();
    if (!silent) setStatus("Stopped");
  }

  function finish() {
    queue = [];
    speaking = false;
    paused = false;
    hideHighlightView();
    updateButtons();
    setStatus("Done");
  }

  // Chrome pauses speech when the tab is hidden for a while; keep the
  // engine alive by nudging it periodically during playback.
  setInterval(() => {
    if (speaking && !paused && synth.paused) {
      synth.resume();
    }
  }, 5000);

  // ---------- Events ----------

  els.speakBtn.addEventListener("click", speak);
  els.pauseBtn.addEventListener("click", pauseOrResume);
  els.stopBtn.addEventListener("click", () => stop());

  els.textInput.addEventListener("input", updateCharCount);

  els.sampleBtn.addEventListener("click", () => {
    els.textInput.value = SAMPLE_TEXT;
    updateCharCount();
    els.textInput.focus();
  });

  els.clearBtn.addEventListener("click", () => {
    stop(true);
    els.textInput.value = "";
    updateCharCount();
    setStatus("Ready");
    els.textInput.focus();
  });

  for (const slider of [els.rate, els.pitch, els.volume]) {
    slider.addEventListener("input", () => {
      updateSliderLabels();
      saveSettings();
    });
  }

  els.voiceSelect.addEventListener("change", saveSettings);

  els.resetBtn.addEventListener("click", () => {
    els.rate.value = 1;
    els.pitch.value = 1;
    els.volume.value = 1;
    updateSliderLabels();
    const defaultVoice = voices.find((v) => v.default) || voices[0];
    if (defaultVoice) els.voiceSelect.value = defaultVoice.voiceURI;
    saveSettings();
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      speak();
    }
    if (event.key === "Escape" && speaking) {
      stop();
    }
  });

  // Stop speech when leaving the page so it doesn't keep talking.
  window.addEventListener("beforeunload", () => synth.cancel());
})();
