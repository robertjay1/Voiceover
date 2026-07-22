import unittest

from voiceover.dialogue import NARRATOR, segment_dialogue, speaker_stats


def speakers_of(segments):
    return [(s.speaker, s.text) for s in segments]


class TestAttribution(unittest.TestCase):
    def test_attribution_after_quote(self):
        segments = segment_dialogue('"The tide is turning," said Elias.')
        self.assertEqual(segments[0].speaker, "Elias")
        self.assertEqual(segments[0].text, "The tide is turning,")
        self.assertEqual(segments[1].speaker, NARRATOR)

    def test_attribution_before_quote(self):
        segments = segment_dialogue('Mira said, "We should go back."')
        dialogue = [s for s in segments if s.is_dialogue]
        self.assertEqual(dialogue[0].speaker, "Mira")

    def test_subject_verb_after_quote(self):
        segments = segment_dialogue('"Get down!" Elias shouted.')
        self.assertEqual(segments[0].speaker, "Elias")

    def test_descriptor_speaker(self):
        segments = segment_dialogue('"Not tonight," growled the old man.')
        self.assertEqual(segments[0].speaker, "the old man")

    def test_titled_name(self):
        segments = segment_dialogue('"Quite so," said Mrs. Higgins.')
        self.assertEqual(segments[0].speaker, "Mrs. Higgins")

    def test_interrupted_quote_same_speaker(self):
        text = (
            '"Ready?" asked Elias.\n\n'
            '"I know," he said, "but the light must stay lit."'
        )
        segments = segment_dialogue(text)
        dialogue = [s for s in segments if s.is_dialogue]
        # The pronoun tag resolves via context, and both halves of the
        # interrupted quote share one speaker.
        self.assertEqual(dialogue[1].speaker, "Elias")
        self.assertEqual(dialogue[1].speaker, dialogue[2].speaker)

    def test_late_attribution_reaches_back(self):
        text = '"Wait." A pause. "It moved," said Mira.'
        segments = segment_dialogue(text)
        dialogue = [s for s in segments if s.is_dialogue]
        self.assertEqual([d.speaker for d in dialogue], ["Mira", "Mira"])


class TestAlternation(unittest.TestCase):
    def test_two_person_alternation(self):
        text = (
            '"Did you see it?" asked Elias.\n\n'
            '"I saw something," said Mira.\n\n'
            '"Out past the rocks?"\n\n'
            '"Past the rocks, and moving fast."'
        )
        segments = [s for s in segment_dialogue(text) if s.is_dialogue]
        self.assertEqual(
            [s.speaker for s in segments],
            ["Elias", "Mira", "Elias", "Mira"],
        )

    def test_pronoun_tag_uses_alternation(self):
        text = (
            '"Ready?" asked Elias.\n\n'
            '"Ready," said Mira.\n\n'
            '"Then jump," he said.'
        )
        segments = [s for s in segment_dialogue(text) if s.is_dialogue]
        self.assertEqual(segments[-1].speaker, "Elias")


class TestSegmentation(unittest.TestCase):
    def test_no_dialogue_is_all_narrator(self):
        segments = segment_dialogue("A plain paragraph.\n\nAnother one.")
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].speaker, NARRATOR)

    def test_narration_between_quotes_kept(self):
        text = '"Hello," said Ana. She looked away. "Goodbye."'
        segments = segment_dialogue(text)
        kinds = [s.speaker for s in segments]
        self.assertEqual(kinds, ["Ana", NARRATOR, "Ana"])
        self.assertIn("She looked away.", segments[1].text)

    def test_curly_quotes(self):
        segments = segment_dialogue("“Steady on,” said Tom.")
        self.assertEqual(segments[0].speaker, "Tom")

    def test_no_words_lost(self):
        text = (
            'Elias climbed the steps. "Storm coming," he muttered. The lamp\n'
            'flickered twice.\n\n"Light it," said Mira. "Now."'
        )
        segments = segment_dialogue(text)
        joined = " ".join(s.text for s in segments)
        for word in ["climbed", "Storm", "flickered", "Light", "Now"]:
            self.assertIn(word, joined)

    def test_unattributed_first_quote_stays_narrator(self):
        segments = segment_dialogue('"Nobody knows who says this."')
        self.assertEqual(segments[0].speaker, NARRATOR)

    def test_speaker_stats(self):
        stats = speaker_stats('"Hi there," said Bo. The rest was silence.')
        self.assertIn("Bo", stats)
        self.assertIn(NARRATOR, stats)


if __name__ == "__main__":
    unittest.main()
