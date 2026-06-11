"""Fast pattern-matching layer.

This is the cheap first line of defence. It scans an incoming prompt for known
prompt-injection and jailbreak signatures before any model is involved, so the
obvious attacks are caught in well under a millisecond and never cost an API
call. Each rule carries a short human-readable reason, which the API surfaces so
a reviewer can see *why* a prompt was flagged.

The patterns here are grouped by attack family. They were seeded from the
labelled cases in the original SCC353 Secure AI coursework (instruction-override,
role-play, social-engineering and multilingual injections) and extended with the
common public jailbreak phrasings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HeuristicHit:
    """A single rule that matched the prompt."""

    category: str
    pattern: str
    reason: str


# Each entry: (category, regex, human-readable reason).
# Regexes are compiled case-insensitively and matched with .search().
_RULES: list[tuple[str, str, str]] = [
    # --- Instruction override ---------------------------------------------
    (
        "instruction_override",
        r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all)\b[^.\n]{0,20}\b(instruction|prompt|task|rule|direction|context)s?\b",  # noqa: E501
        "Attempts to make the model ignore its previous instructions.",
    ),
    (
        "instruction_override",
        r"\b(forget|ignore)\b[^.\n]{0,20}\beverything\b",
        "Tries to wipe the model's existing context or instructions.",
    ),
    (
        "instruction_override",
        r"\bnew\b[^.\n]{0,15}\b(task|instruction|rule|objective|mission)s?\b[^.\n]{0,30}\b(now|instead|focus)\b",  # noqa: E501
        "Tries to replace the model's task with an attacker-supplied one.",
    ),
    # --- System prompt / secret extraction --------------------------------
    (
        "prompt_extraction",
        r"\b(show|reveal|print|repeat|display|tell|give|output|leak)\b[^.\n]{0,40}\b(system|initial|hidden|original|your)\b[^.\n]{0,20}\b(prompt|instruction|rule|directive|message)s?\b",  # noqa: E501
        "Attempts to extract the hidden system prompt or instructions.",
    ),
    (
        "prompt_extraction",
        r"\b(what|repeat)\b[^.\n]{0,30}\b(was|were|are)\b[^.\n]{0,20}\b(you|your)\b[^.\n]{0,15}\b(told|instructed|programmed|configured)\b",  # noqa: E501
        "Probes for the model's underlying configuration or instructions.",
    ),
    (
        "secret_extraction",
        r"\b(api[_\s-]?key|password|secret|token|credential|private key|\.env)\b",
        "References secrets or credentials that should never be disclosed.",
    ),
    # --- Role-play / persona override -------------------------------------
    (
        "roleplay_override",
        r"\b(you are|act as|pretend to be|roleplay as|imagine you are|from now on you are)\b[^.\n]{0,40}\b(dan|jailbroken|unfiltered|unrestricted|no restrictions|evil|developer mode)\b",  # noqa: E501
        "Tries to put the model into an unrestricted persona (jailbreak).",
    ),
    (
        "roleplay_override",
        r"\bdeveloper mode\b|\bdo anything now\b|\bDAN\b",
        "Invokes a known jailbreak persona ('DAN' / developer mode).",
    ),
    (
        "roleplay_override",
        r"\b(stay in character|never break character|without falling out of (the )?role)\b",
        "Insists the model never leave an assigned role, a common jailbreak frame.",
    ),
    # --- Social engineering / urgency -------------------------------------
    (
        "social_engineering",
        r"\b(urgent(ly)?|immediately|right now|stop everything|attention[ ,-]+stop)\b[^.\n]{0,40}\b(help|need|do|task|question)\b",  # noqa: E501
        "Uses urgency/pressure framing typical of social-engineering attacks.",
    ),
    (
        "social_engineering",
        r"\b(this is (a )?test|just (a )?hypothetical|for (educational|research) purposes only)\b[^.\n]{0,40}\b(so|therefore|now|please)\b",  # noqa: E501
        "Disguises a request as a harmless test or hypothetical to lower guards.",
    ),
    # --- Output-format hijack ---------------------------------------------
    (
        "format_hijack",
        r"\b(begin your (answer|reply|response) with|start (your )?(answer|reply) with|respond only with|you must say)\b",  # noqa: E501
        "Tries to seed or constrain the model's output, a known injection trick.",
    ),
]

_COMPILED: list[tuple[str, re.Pattern[str], str]] = [
    (category, re.compile(pattern, re.IGNORECASE), reason)
    for category, pattern, reason in _RULES
]

# Scripts whose presence mid-prompt (when the prompt is mostly Latin) often
# signals a multilingual injection trying to smuggle instructions past an
# English-only filter -- the exact blind spot called out in the coursework.
_NON_LATIN = re.compile(
    r"[Ѐ-ӿ]"          # Cyrillic
    r"|[؀-ۿ]"         # Arabic
    r"|[一-鿿]"         # CJK
    r"|[぀-ヿ]"         # Hiragana/Katakana
    r"|[가-힯]"         # Hangul
)

# Injection verbs in a few languages, used only to corroborate a mixed-script
# prompt (keeps the multilingual rule from firing on innocent foreign text).
_FOREIGN_INJECTION = re.compile(
    r"\b(olvida|ignora|wykonaj|zignoruj|vergiss|ignorier|oublie|игнорир|忘记|無視)\w*\b",
    re.IGNORECASE,
)


def scan(prompt: str) -> list[HeuristicHit]:
    """Return every heuristic rule that matched ``prompt`` (possibly empty)."""

    hits: list[HeuristicHit] = []
    for category, regex, reason in _COMPILED:
        match = regex.search(prompt)
        if match:
            hits.append(
                HeuristicHit(
                    category=category,
                    pattern=match.group(0).strip(),
                    reason=reason,
                )
            )

    # Multilingual injection: a predominantly Latin prompt that suddenly
    # switches script AND contains a foreign instruction verb.
    latin = sum(1 for ch in prompt if ch.isascii() and ch.isalpha())
    non_latin = len(_NON_LATIN.findall(prompt))
    mixed_script = latin > 20 and non_latin > 0
    if (mixed_script and _NON_LATIN.search(prompt)) or _FOREIGN_INJECTION.search(prompt):
        if _FOREIGN_INJECTION.search(prompt) or mixed_script:
            hits.append(
                HeuristicHit(
                    category="multilingual_injection",
                    pattern="mixed-script / foreign instruction",
                    reason=(
                        "Switches language mid-prompt, a technique used to slip "
                        "instructions past an English-only filter."
                    ),
                )
            )
    return hits
