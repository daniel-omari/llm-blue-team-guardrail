"""Undo common obfuscation before the rules run.

Attackers disguise injections so that a pattern match on the raw text misses them,
while the model reading the text still understands them. This module produces a
plain copy of the text for the rules to match against, and reports what it had to
undo, since the disguise itself is evidence:

- **Unicode compatibility forms** (NFKC): fullwidth letters, mathematical bold or
  italic letters and ligatures fold to plain ASCII, e.g. "𝐢𝐠𝐧𝐨𝐫𝐞" -> "ignore".
- **Invisible characters**: zero-width spaces and joiners, soft hyphens and bidi
  controls are removed, so "ig\u200bnore" matches "ignore".
- **Unicode tag characters** (U+E0000 block): invisible to people but read by many
  models, so they can smuggle a whole hidden instruction ("ASCII smuggling"). Their
  hidden text is decoded and scanned. The one legitimate use, subdivision flag emoji
  such as the Scottish flag, is recognised and left alone.
- **Homoglyphs**: Cyrillic and Greek look-alike letters inside an otherwise Latin
  word ("іgnоrе" with Cyrillic і, о, е) are mapped back to Latin. Words written fully
  in another script are left as they are, so real Russian or Greek text is untouched.
- **Base64**: long base64 runs that decode to readable text are decoded and scanned.

None of this changes what the caller sent or what the judge reads: the judge gets
the original text, plus a note of any hidden content the guardrail uncovered.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field

# Zero-width and formatting characters that render as nothing (or reorder text).
_INVISIBLE = re.compile(
    "[\u00ad\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]"
)

# Unicode tag characters: U+E0020-U+E007E mirror printable ASCII; U+E007F cancels.
_TAG_RUN = re.compile("[\U000e0000-\U000e007f]+")
_BLACK_FLAG = "\U0001f3f4"     # a subdivision flag is this followed by tag letters

# Look-alike letters that are mapped to Latin inside mixed-script words.
_HOMOGLYPHS = str.maketrans({
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p",
    "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d",
    "ԛ": "q", "ԝ": "w", "ɡ": "g", "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M",
    "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J",
    "Ѕ": "S",
    # Greek
    "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
    "υ": "u", "χ": "x", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I",
    "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})
_WORD = re.compile(r"\w+")
_LATIN = re.compile(r"[A-Za-z]")
_LOOKALIKE = re.compile("[" + "".join(
    ch for ch in map(chr, range(0x370, 0x530)) if ch.translate(_HOMOGLYPHS) != ch
) + "ɡ]")

# Base64 runs long enough to carry an instruction (24+ chars, about 18 bytes).
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")


@dataclass
class Signal:
    """Something the normaliser had to undo, reported like a heuristic finding."""

    category: str
    pattern: str
    reason: str


@dataclass
class Normalized:
    text: str                                         # plain copy for the rules
    hidden: list[str] = field(default_factory=list)   # decoded hidden content
    signals: list[Signal] = field(default_factory=list)


def _tags(text: str, out: Normalized) -> str:
    """Decode tag-character runs that aren't part of a flag emoji, and drop them."""

    def replace(m: re.Match[str]) -> str:
        if m.start() > 0 and text[m.start() - 1] == _BLACK_FLAG:
            return m.group(0)                          # a subdivision flag
        decoded = "".join(chr(ord(c) - 0xE0000) for c in m.group(0)
                          if 0xE0020 <= ord(c) <= 0xE007E)
        if decoded.strip():
            out.hidden.append(decoded)
        return ""

    return _TAG_RUN.sub(replace, text)


def _fold_homoglyphs(text: str) -> tuple[str, bool]:
    """Map look-alike letters to Latin, only in words that also contain Latin."""
    found = False

    def fold(m: re.Match[str]) -> str:
        nonlocal found
        word = m.group(0)
        if _LATIN.search(word) and _LOOKALIKE.search(word):
            found = True
            return word.translate(_HOMOGLYPHS)
        return word

    return _WORD.sub(fold, text), found


def _decode_base64(text: str) -> list[str]:
    """Readable text hidden in base64 runs (binary data such as images is ignored)."""
    decoded: list[str] = []
    for m in _BASE64.finditer(text):
        blob = m.group(0)
        try:
            raw = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True)
            plain = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        printable = sum(ch.isprintable() or ch.isspace() for ch in plain)
        letters = sum(ch.isalpha() for ch in plain)
        if plain and printable / len(plain) > 0.95 and letters / len(plain) > 0.5:
            decoded.append(plain)
    return decoded


def normalize(text: str) -> Normalized:
    """Return a plain copy of ``text`` for matching, plus any hidden content."""

    out = Normalized(text="")
    plain = _tags(text, out)
    if out.hidden:
        out.signals.append(Signal(
            "unicode_smuggling", "invisible Unicode tag characters",
            "Hides text in invisible Unicode tag characters that people can't see "
            "but models read (ASCII smuggling).",
        ))

    folded = unicodedata.normalize("NFKC", plain)
    without_invisible = _INVISIBLE.sub("", folded)
    # Only worth reporting when invisible characters sit inside words, where they
    # break up a phrase; a stray zero-width space between words is common in pastes.
    if re.search(r"\w[\u00ad\u200b-\u200f\u2060-\u2064\ufeff]+\w", folded):
        out.signals.append(Signal(
            "invisible_characters", "zero-width or formatting characters inside words",
            "Breaks words up with invisible characters, a way to dodge pattern filters.",
        ))

    plain, homoglyphs = _fold_homoglyphs(without_invisible)
    if homoglyphs:
        out.signals.append(Signal(
            "homoglyphs", "look-alike letters from another alphabet",
            "Mixes look-alike Cyrillic or Greek letters into Latin words to dodge filters.",
        ))

    encoded = _decode_base64(plain)
    if encoded:
        out.hidden.extend(encoded)
        out.signals.append(Signal(
            "encoded_payload", "base64-encoded text",
            "Contains base64 that decodes to readable text; the decoded text was screened too.",
        ))

    out.text = plain
    return out
