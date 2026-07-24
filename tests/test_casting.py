import unittest

from voiceover.casting import (
    VoiceAllocator,
    autocast,
    group_full_name_aliases,
    infer_accent,
    infer_age,
    infer_gender,
    infer_traits,
)
from voiceover.voicebank import VoiceProfile, slugify


class TestGender(unittest.TestCase):
    def test_first_name_lexicon(self):
        self.assertEqual(infer_gender("Kayleigh", "", {"Kayleigh"}), "female")
        self.assertEqual(infer_gender("Marcus", "", {"Marcus"}), "male")

    def test_honorific_wins(self):
        self.assertEqual(infer_gender("Painter", "Mrs Painter smiled.", {"Painter"}), "female")

    def test_pronoun_fallback_for_surname(self):
        text = "Voss checked his watch. He frowned. Voss sighed and shut his laptop."
        self.assertEqual(infer_gender("Voss", text, {"Voss"}), "male")

    def test_truncation_does_not_false_match_title(self):
        # "...forms. Ray" must not read "ms." as the honorific "Ms".
        text = "He filled the forms. Ray said nothing. Ray was a quiet man; he drove."
        self.assertEqual(infer_gender("Ray", text, {"Ray"}), "male")


class TestAge(unittest.TestCase):
    def test_older_cue(self):
        self.assertEqual(infer_age("Ray", "Ray was in his sixties, near retirement."), "older")

    def test_no_false_older_from_old_friend(self):
        self.assertEqual(infer_age("James", "James, an old friend, grinned."), "adult")

    def test_child_cue(self):
        self.assertEqual(infer_age("Tom", "Tom was a small child, a toddler really."), "child")


class TestAccent(unittest.TestCase):
    def test_explicit_caribbean_flagged(self):
        region, explicit, note = infer_accent("Horace", "Horace began life in the West Indies.")
        self.assertEqual(region, "za")
        self.assertTrue(explicit)
        self.assertIn("Caribbean", note)

    def test_default_when_no_cue(self):
        region, explicit, _ = infer_accent("Bob", "Bob went to the shop.", default_region="gb")
        self.assertEqual((region, explicit), ("gb", False))

    def test_setting_default_for_canada(self):
        text = "Gill drove through Ontario past the RCMP post in Kamloops. Gill parked."
        region, explicit, _ = infer_accent("Gill", text, default_region="gb")
        self.assertEqual(region, "ca")
        self.assertFalse(explicit)


class TestAliases(unittest.TestCase):
    def test_full_name_links_first_and_surname(self):
        canon = group_full_name_aliases(["Brent", "Kowalski"],
                                        "Brent Kowalski signed it. Kowalski left.")
        self.assertEqual(canon["Brent"], canon["Kowalski"])


class TestAllocator(unittest.TestCase):
    def test_distinct_voices_for_same_traits(self):
        from voiceover.casting import Traits
        alloc = VoiceAllocator("gb")
        seen = set()
        for _ in range(8):
            p = alloc.allocate(Traits(gender="male", region="gb"))
            key = (p.voice, p.rate, p.pitch)
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_no_far_accent_without_explicit_cue(self):
        from voiceover.casting import Traits
        alloc = VoiceAllocator("gb")
        for _ in range(12):
            p = alloc.allocate(Traits(gender="male", region="gb", accent_explicit=False))
            self.assertFalse(p.voice.startswith(("en-ZA", "en-KE", "en-NG", "en-IN",
                                                 "en-HK", "en-SG", "en-PH")))

    def test_explicit_far_accent_honoured(self):
        from voiceover.casting import Traits
        alloc = VoiceAllocator("gb")
        p = alloc.allocate(Traits(gender="male", region="za", accent_explicit=True))
        self.assertTrue(p.voice.startswith("en-ZA"))

    def test_child_voice_only_for_child(self):
        from voiceover.casting import Traits
        alloc = VoiceAllocator("gb")
        voices = [alloc.allocate(Traits(gender="female", region="gb")).voice for _ in range(4)]
        self.assertNotIn("en-GB-MaisieNeural", voices)


class TestAutocast(unittest.TestCase):
    def test_recurring_character_reused_from_bank(self):
        bank = {"james": VoiceProfile(engine="edge", voice="en-GB-RyanNeural")}
        narrator = VoiceProfile(engine="edge", voice="en-US-AndrewMultilingualNeural")
        text = "James nodded. Sandra typed."
        entries = autocast(["James", "Sandra"], text, bank=bank, narrator=narrator)
        james = next(e for e in entries if e.canonical == "James")
        self.assertTrue(james.reused)
        self.assertEqual(james.profile.voice, "en-GB-RyanNeural")

    def test_every_character_distinct(self):
        narrator = VoiceProfile(engine="edge", voice="en-US-AndrewMultilingualNeural")
        speakers = ["James", "Sandra", "Marcus", "Priya", "Gavin", "Dawn"]
        text = " ".join(f"{s} spoke." for s in speakers)
        entries = autocast(speakers, text, bank={}, narrator=narrator)
        keys = {(e.profile.voice, e.profile.rate, e.profile.pitch) for e in entries}
        self.assertEqual(len(keys), len(speakers))

    def test_slugify(self):
        self.assertEqual(slugify("DS Anna Okoye"), "anna-okoye")
        self.assertEqual(slugify("Dr Voss"), "voss")


if __name__ == "__main__":
    unittest.main()
