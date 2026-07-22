import unittest

from voiceover.chunking import chunk_text, split_sentences


class TestSentences(unittest.TestCase):
    def test_basic_split(self):
        self.assertEqual(
            split_sentences("One. Two! Three?"),
            ["One.", "Two!", "Three?"],
        )

    def test_closing_quotes(self):
        sentences = split_sentences('"Stop!" she said. He did not.')
        self.assertEqual(sentences, ['"Stop!" she said.', "He did not."])


class TestChunking(unittest.TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(chunk_text("Hello world."), ["Hello world."])

    def test_respects_max_chars(self):
        text = " ".join(f"Sentence number {i} is here." for i in range(200))
        chunks = chunk_text(text, max_chars=200)
        self.assertTrue(all(len(c) <= 200 for c in chunks))
        self.assertGreater(len(chunks), 1)

    def test_no_text_lost(self):
        text = "\n\n".join(f"Paragraph {i}. " + "Word " * 50 for i in range(20))
        chunks = chunk_text(text, max_chars=300)
        original_words = text.split()
        chunk_words = " ".join(chunks).split()
        self.assertEqual(original_words, chunk_words)

    def test_paragraphs_preferred_as_boundaries(self):
        text = "First paragraph here.\n\nSecond paragraph here."
        chunks = chunk_text(text, max_chars=30)
        self.assertEqual(len(chunks), 2)

    def test_giant_unbroken_sentence(self):
        text = "word " * 500  # no punctuation at all
        chunks = chunk_text(text.strip(), max_chars=200)
        self.assertTrue(all(len(c) <= 200 for c in chunks))
        self.assertEqual(" ".join(chunks).split(), text.split())

    def test_empty(self):
        self.assertEqual(chunk_text("   "), [])


if __name__ == "__main__":
    unittest.main()
