"""Output-side check on generated RAG answers.

Screening every retrieved chunk is the main defence, but no screen is perfect. If an
injection slipped through, its payoff usually shows up in the *answer*: a link or
email address the attacker wants the user to visit or write to (phishing, data
exfiltration), a markdown image whose URL carries data out the moment it renders,
or the assistant's own hidden instructions repeated back. Those are cheap to check:

- every link and email address in the answer must appear in the clean sources the
  model was given;
- no markdown images at all (the assistant has no reason to embed one);
- no run of eight or more consecutive words from the system prompt.

A failing answer is withheld, and the caller is told why.
"""

from __future__ import annotations

import re

_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>()\[\]{}\"']+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_WORDS = re.compile(r"[a-z0-9']+")
LEAK_RUN = 8          # this many consecutive system-prompt words count as a leak


def _words(text: str) -> list[str]:
    return _WORDS.findall(text.lower())


def check_answer(answer: str, sources: list[str], system_prompt: str) -> list[str]:
    """Problems with ``answer`` given the sources it was built from (empty = fine)."""

    issues: list[str] = []
    source_text = "\n".join(sources).lower()

    for url in sorted({u.rstrip(".,;:!?") for u in _URL.findall(answer)}):
        if url.lower() not in source_text:
            issues.append(f"links to {url}, which is not in the sources")
    for email in sorted(set(_EMAIL.findall(answer))):
        if email.lower() not in source_text:
            issues.append(f"mentions the email address {email}, which is not in the sources")
    if _MD_IMAGE.search(answer):
        issues.append("embeds an image, which can leak data through its URL")

    system = _words(system_prompt)
    answer_words = " " + " ".join(_words(answer)) + " "
    for i in range(len(system) - LEAK_RUN + 1):
        if " " + " ".join(system[i:i + LEAK_RUN]) + " " in answer_words:
            issues.append("repeats the assistant's hidden instructions")
            break

    return issues
