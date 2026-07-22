import tempfile
import unittest
from pathlib import Path

from voiceover.chapters import load_chapters, split_chapters


class TestMarkdownChapters(unittest.TestCase):
    def test_headings_split(self):
        text = "# One\n\nFirst body.\n\n# Two\n\nSecond body."
        chapters = split_chapters(text)
        self.assertEqual([c.title for c in chapters], ["One", "Two"])
        self.assertEqual(chapters[0].text, "First body.")

    def test_preamble_kept(self):
        text = "Intro before headings.\n\n# One\n\nBody."
        chapters = split_chapters(text)
        self.assertEqual(chapters[0].title, "Preamble")
        self.assertIn("Intro", chapters[0].text)

    def test_markdown_stripped(self):
        text = "# T\n\nSome **bold** and a [link](https://x.com) and `code`."
        chapters = split_chapters(text)
        self.assertEqual(chapters[0].text, "Some bold and a link and code.")

    def test_h3_not_a_chapter(self):
        text = "# One\n\nBody.\n\n### Subsection\n\nMore."
        chapters = split_chapters(text)
        self.assertEqual(len(chapters), 1)


class TestPlainChapters(unittest.TestCase):
    def test_chapter_lines(self):
        text = "Chapter 1\n\nFirst.\n\nChapter 2\n\nSecond."
        chapters = split_chapters(text, markdown=False)
        self.assertEqual([c.title for c in chapters], ["Chapter 1", "Chapter 2"])

    def test_roman_numerals_and_named_parts(self):
        text = "CHAPTER XII\n\nBody one.\n\nPart Two: The Return\n\nBody two.\n\nEpilogue\n\nEnd."
        chapters = split_chapters(text, markdown=False)
        self.assertEqual(len(chapters), 3)
        self.assertEqual(chapters[2].title, "Epilogue")

    def test_mid_sentence_chapter_word_not_split(self):
        text = "I read a chapter 3 times yesterday.\nIt was fine."
        chapters = split_chapters(text, markdown=False)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "Full Text")

    def test_no_structure_falls_back_to_single(self):
        chapters = split_chapters("Just a plain paragraph.", markdown=False)
        self.assertEqual(len(chapters), 1)

    def test_empty_input(self):
        self.assertEqual(split_chapters("   \n  "), [])


class TestDirectoryInput(unittest.TestCase):
    def test_files_become_chapters_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "02_second_part.txt").write_text("Second file text.")
            (root / "01_first_part.txt").write_text("First file text.")
            (root / "notes.json").write_text("{}")
            chapters = load_chapters(root)
        self.assertEqual([c.title for c in chapters], ["first part", "second part"])
        self.assertEqual(chapters[0].text, "First file text.")

    def test_missing_input_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_chapters(Path("/nonexistent/book.txt"))


if __name__ == "__main__":
    unittest.main()
