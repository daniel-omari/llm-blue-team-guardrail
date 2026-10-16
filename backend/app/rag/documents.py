"""Load the knowledge-base pages and split them into chunks for retrieval.

Pages are Markdown: a "# Title" line, then "## Section" headings. Each section
becomes one chunk (split further if it is long), and the page title is kept with
every chunk so search results and answers can name their source.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

CORPUS_DIR = pathlib.Path(__file__).parent / "corpus"
MAX_CHUNK_CHARS = 900


@dataclass(frozen=True)
class Chunk:
    id: str          # stable id, e.g. "travel-and-expenses#2"
    source: str      # file name the chunk came from
    title: str       # page title
    section: str     # section heading
    text: str        # the section's text (without the heading)


def _split_long(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text that is too long at paragraph, then sentence, boundaries."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_page(source: str, markdown: str) -> list[Chunk]:
    """Turn one Markdown page into chunks, one per "## " section."""
    title = source
    sections: list[tuple[str, list[str]]] = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)

    chunks: list[Chunk] = []
    stem = source.removesuffix(".md")
    for heading, lines in sections:
        # Join wrapped lines into flowing paragraphs.
        text = re.sub(r"\s+", " ", " ".join(lines)).strip()
        for piece in _split_long(text) if text else []:
            chunks.append(Chunk(f"{stem}#{len(chunks) + 1}", source, title, heading, piece))
    return chunks


def load_corpus(directory: pathlib.Path = CORPUS_DIR) -> list[Chunk]:
    """Every chunk of every page in the corpus (the folder's README is not indexed)."""
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        chunks.extend(chunk_page(path.name, path.read_text(encoding="utf-8")))
    return chunks
