import tempfile
import unittest
import wave
from pathlib import Path

from voiceover.audio import concat_audio, duration_seconds


def write_tone_wav(path: Path, seconds: float = 0.25, framerate: int = 22050) -> None:
    frames = int(seconds * framerate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x01" * frames)


class TestAudio(unittest.TestCase):
    def test_wav_concat_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parts = [root / f"{i}.wav" for i in range(3)]
            for part in parts:
                write_tone_wav(part, seconds=0.25)
            out = root / "joined.wav"
            concat_audio(parts, out)
            self.assertAlmostEqual(duration_seconds(out), 0.75, delta=0.02)

    def test_single_file_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "only.wav"
            write_tone_wav(src)
            out = root / "out.wav"
            concat_audio([src], out)
            self.assertEqual(out.read_bytes(), src.read_bytes())


if __name__ == "__main__":
    unittest.main()
