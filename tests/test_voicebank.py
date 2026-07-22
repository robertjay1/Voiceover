import json
import tempfile
import unittest
from pathlib import Path

from voiceover.voicebank import Cast, VoiceProfile, load_bank, save_bank


class TestBank(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bank.json"
            bank = {
                "gruff": VoiceProfile(engine="edge", voice="en-GB-RyanNeural", rate=0.92),
            }
            save_bank(bank, path)
            loaded = load_bank(path)
        self.assertEqual(loaded["gruff"].voice, "en-GB-RyanNeural")
        self.assertEqual(loaded["gruff"].rate, 0.92)

    def test_missing_bank_is_empty(self):
        self.assertEqual(load_bank(Path("/nonexistent/bank.json")), {})


class TestCast(unittest.TestCase):
    def _narrator(self):
        return VoiceProfile(engine="edge", voice="en-US-AndrewMultilingualNeural")

    def test_cast_file_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            cast_path = Path(tmp) / "cast.json"
            cast_path.write_text(json.dumps({
                "narrator": "en-US-AvaMultilingualNeural",
                "Elias": "gruff",
                "Mira": {"voice": "en-GB-SoniaNeural", "rate": 1.1},
            }))
            bank = {"gruff": VoiceProfile(engine="espeak", voice="en+m3")}
            cast = Cast.load(cast_path, bank, "edge", self._narrator())
        self.assertEqual(cast.mapping["Elias"].engine, "espeak")
        self.assertEqual(cast.mapping["Mira"].voice, "en-GB-SoniaNeural")
        self.assertEqual(cast.mapping["Mira"].rate, 1.1)
        self.assertEqual(cast.mapping["narrator"].voice, "en-US-AvaMultilingualNeural")

    def test_auto_assignment_distinct_and_stable(self):
        cast = Cast(default_engine="edge", narrator_profile=self._narrator())
        a = cast.profile_for("Alice")
        b = cast.profile_for("Bob")
        again = cast.profile_for("Alice")
        self.assertNotEqual(a.voice, b.voice)
        self.assertNotEqual(a.voice, self._narrator().voice)
        self.assertEqual(a.voice, again.voice)

    def test_narrator_falls_through(self):
        narrator = self._narrator()
        cast = Cast(default_engine="edge", narrator_profile=narrator)
        self.assertEqual(cast.profile_for("narrator").voice, narrator.voice)

    def test_pool_exhaustion_falls_back_to_narrator(self):
        narrator = VoiceProfile(engine="piper", voice="model")
        cast = Cast(default_engine="piper", narrator_profile=narrator)
        self.assertEqual(cast.profile_for("Anyone").voice, "model")


if __name__ == "__main__":
    unittest.main()
