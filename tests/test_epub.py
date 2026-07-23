import tempfile
import unittest
import zipfile
from pathlib import Path

from voiceover.chapters import load_chapters
from voiceover.epub import book_title, load_epub_chapters

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:identifier id="uid">test-1</dc:identifier>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="c2" href="text/two.xhtml" media-type="application/xhtml+xml"/>
    <item id="c1" href="text/one.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
    <itemref idref="nav" linear="no"/>
  </spine>
</package>"""

CHAPTER_ONE = """<html xmlns="http://www.w3.org/1999/xhtml"><head>
<title>ignore me</title><style>p { color: red }</style></head>
<body><h1>Chapter One</h1>
<p>&ldquo;Hello,&rdquo; said Ana &amp; waved.</p>
<p>Second paragraph.</p></body></html>"""

CHAPTER_TWO = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<h1>Chapter Two</h1><p>More text here.</p></body></html>"""

NAV = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<nav><ol><li>Chapter One</li></ol></nav></body></html>"""


def write_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("EPUB/content.opf", OPF)
        z.writestr("EPUB/text/one.xhtml", CHAPTER_ONE)
        z.writestr("EPUB/text/two.xhtml", CHAPTER_TWO)
        z.writestr("EPUB/nav.xhtml", NAV)
        z.writestr("EPUB/style.css", "p { color: red }")


class TestEpub(unittest.TestCase):
    def _make(self, tmp: str) -> Path:
        path = Path(tmp) / "book.epub"
        write_epub(path)
        return path

    def test_spine_order_and_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapters = load_epub_chapters(self._make(tmp))
        self.assertEqual([c.title for c in chapters], ["Chapter One", "Chapter Two"])

    def test_text_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapters = load_epub_chapters(self._make(tmp))
        text = chapters[0].text
        self.assertIn("“Hello,” said Ana & waved.", text)
        self.assertIn("Second paragraph.", text)
        self.assertNotIn("ignore me", text)   # <title> skipped
        self.assertNotIn("color", text)       # <style> skipped
        self.assertFalse(text.startswith("Chapter One"))  # heading not narrated twice

    def test_nav_document_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapters = load_epub_chapters(self._make(tmp))
        self.assertEqual(len(chapters), 2)

    def test_book_title_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(book_title(self._make(tmp)), "Test Book")

    def test_load_chapters_dispatches_epub(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapters = load_chapters(self._make(tmp))
        self.assertEqual(len(chapters), 2)

    def test_not_a_zip_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.epub"
            bad.write_text("not a zip")
            with self.assertRaises(ValueError):
                load_epub_chapters(bad)


if __name__ == "__main__":
    unittest.main()
