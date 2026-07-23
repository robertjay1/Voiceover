"""EPUB input: extract chapters from .epub files using only the stdlib.

An EPUB is a zip archive of XHTML documents plus an OPF manifest that
defines reading order (the "spine"). We follow the spine, pull readable
text out of each document, and use its first heading as the chapter
title — no third-party dependencies required.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from .chapters import Chapter

_CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
_OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}


class _TextExtractor(HTMLParser):
    """Pull narratable text out of an XHTML document."""

    _BLOCK_TAGS = {
        "p", "div", "section", "article", "blockquote", "li", "tr",
        "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr",
    }
    _SKIP_TAGS = {"style", "script", "head", "title"}
    _HEADING_TAGS = {"h1", "h2", "h3"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.heading: str | None = None
        self._skip_depth = 0
        self._heading_parts: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n\n")
        if tag in self._HEADING_TAGS and self.heading is None:
            self._heading_parts = []

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n\n")
        if tag in self._HEADING_TAGS and self._heading_parts is not None:
            heading = " ".join("".join(self._heading_parts).split())
            if heading:
                self.heading = heading
            self._heading_parts = None

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._heading_parts is not None:
            self._heading_parts.append(data)
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", raw)]
        return "\n\n".join(p for p in paragraphs if p)


def _opf_path(archive: zipfile.ZipFile) -> str:
    container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
    rootfile = container.find(".//c:rootfile", _CONTAINER_NS)
    if rootfile is None or not rootfile.get("full-path"):
        raise ValueError("Malformed EPUB: no rootfile in META-INF/container.xml")
    return rootfile.get("full-path")


def _spine_documents(archive: zipfile.ZipFile, opf_path: str) -> list[str]:
    """Document paths in reading order."""
    opf = ElementTree.fromstring(archive.read(opf_path))
    base = posixpath.dirname(opf_path)

    manifest: dict[str, str] = {}
    nav_ids: set[str] = set()
    for item in opf.findall(".//opf:manifest/opf:item", _OPF_NS):
        item_id, href = item.get("id"), item.get("href")
        if not item_id or not href:
            continue
        media = item.get("media-type", "")
        if "html" not in media and "xml" not in media:
            continue
        manifest[item_id] = posixpath.normpath(posixpath.join(base, href))
        if "nav" in (item.get("properties") or ""):
            nav_ids.add(item_id)

    documents = []
    for itemref in opf.findall(".//opf:spine/opf:itemref", _OPF_NS):
        if itemref.get("linear", "yes") == "no":
            continue
        idref = itemref.get("idref")
        if idref in manifest and idref not in nav_ids:
            documents.append(manifest[idref])
    return documents


def book_title(path: Path) -> str | None:
    """The dc:title from the EPUB's metadata, if present."""
    try:
        with zipfile.ZipFile(path) as archive:
            opf = ElementTree.fromstring(archive.read(_opf_path(archive)))
        title = opf.find(".//dc:title", _OPF_NS)
        return title.text.strip() if title is not None and title.text else None
    except (zipfile.BadZipFile, KeyError, ValueError, ElementTree.ParseError):
        return None


def load_epub_chapters(path: Path) -> list[Chapter]:
    """One chapter per spine document that contains real text."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Not a valid EPUB (not a zip archive): {path}") from exc

    chapters: list[Chapter] = []
    with archive:
        for number, doc_path in enumerate(_spine_documents(archive, _opf_path(archive)), 1):
            try:
                html = archive.read(doc_path).decode("utf-8", errors="replace")
            except KeyError:
                continue
            extractor = _TextExtractor()
            extractor.feed(html)
            text = extractor.text()
            title = extractor.heading or Path(doc_path).stem
            # Drop the title line if it's repeated as the first text line.
            if extractor.heading and text.startswith(extractor.heading):
                text = text[len(extractor.heading):].lstrip()
            if text.split():
                chapters.append(Chapter(title=title, text=text))

    if not chapters:
        raise ValueError(f"No readable chapters found in {path}")
    return chapters
