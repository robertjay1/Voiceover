import tempfile
import unittest
import wave
from pathlib import Path

from voiceover.cli import main
from voiceover.engines import CHUNK_LIMITS
from voiceover.engines.kokoro import parse_blend
from voiceover.engines.base import EngineError
from voiceover.voicebank import VoiceProfile, load_bank


class TestBlendParsing(unittest.TestCase):
    def test_single_voice(self):
        self.assertEqual(parse_blend("af_heart"), [("af_heart", 1.0)])

    def test_weighted_blend_normalizes(self):
        blend = parse_blend("af_heart*0.6+af_sky*0.2")
        self.assertEqual([name for name, _ in blend], ["af_heart", "af_sky"])
        self.assertAlmostEqual(blend[0][1], 0.75)
        self.assertAlmostEqual(blend[1][1], 0.25)

    def test_equal_weights_by_default(self):
        blend = parse_blend("af_heart+af_sky")
        self.assertAlmostEqual(blend[0][1], 0.5)

    def test_bad_weight_rejected(self):
        with self.assertRaises(EngineError):
            parse_blend("af_heart*fast")
        with self.assertRaises(EngineError):
            parse_blend("af_heart*0")


class TestCloneProfiles(unittest.TestCase):
    def test_profile_key_distinguishes_samples(self):
        a = VoiceProfile(engine="chatterbox", sample="/tmp/alice.wav")
        b = VoiceProfile(engine="chatterbox", sample="/tmp/bob.wav")
        self.assertNotEqual(a.key(), b.key())

    def test_clone_label_shows_sample(self):
        profile = VoiceProfile(engine="chatterbox", sample="/tmp/alice.wav")
        self.assertIn("alice.wav", profile.label())

    def test_old_bank_files_still_load(self):
        # Banks saved before the sample/exaggeration fields existed.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bank.json"
            path.write_text('{"old": {"engine": "edge", "voice": "x", '
                            '"rate": 1.0, "volume": 1.0, "model_dir": null}}')
            bank = load_bank(path)
        self.assertIsNone(bank["old"].sample)


class TestCloneCommand(unittest.TestCase):
    def test_missing_sample_fails(self):
        code = main(["clone", "me", "--sample", "/nonexistent/me.wav",
                     "--bank", "/tmp/unused-bank.json"])
        self.assertEqual(code, 1)

    def test_clone_saves_bank_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "me.wav"
            with wave.open(str(sample), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(b"\x00\x01" * 22050 * 12)
            bank_path = Path(tmp) / "bank.json"
            code = main(["clone", "my-voice", "--sample", str(sample),
                         "--bank", str(bank_path)])
            self.assertEqual(code, 0)
            bank = load_bank(bank_path)
        self.assertEqual(bank["my-voice"].engine, "chatterbox")
        self.assertEqual(bank["my-voice"].sample, str(sample))


class TestChunkLimits(unittest.TestCase):
    def test_chatterbox_capped(self):
        self.assertLessEqual(CHUNK_LIMITS["chatterbox"], 500)

    def test_limit_matches_engine_attr(self):
        from voiceover.engines.chatterbox import ChatterboxEngine

        self.assertEqual(
            CHUNK_LIMITS["chatterbox"], ChatterboxEngine.preferred_chunk_chars
        )


if __name__ == "__main__":
    unittest.main()
