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

Heuristics are deliberately a coarse first pass: they trade precision for speed
and are inherently evadable, which is exactly why the design escalates the
ambiguous middle ground to the LLM judge. Two cheap measures here reduce the
most obvious failure modes: rules look for an *action/context* around sensitive
nouns (so a bare mention of "token" is not flagged), and matching also runs over
a de-obfuscated copy of the prompt so trivial leetspeak ("p4ssw0rd") still hits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.guardrail.normalize import normalize


@dataclass(frozen=True)
class HeuristicHit:
    """A single rule that matched the prompt."""

    category: str
    pattern: str
    reason: str


# Each entry: (category, regex, human-readable reason).
# Regexes are compiled case-insensitively and matched with .search().

# Names for the guardrail itself, used by the judge-manipulation rules below. Kept
# specific ("safety filter", not "filter"; "AI moderator", not "moderator") so that
# ordinary text about spam folders or forum moderators is not flagged.
_GUARD = (
    r"(guardrails?|classifier|(?:prompt|injection|safety|content|security)[ -]"
    r"(?:classifier|filter|checker|scanner)|safety (?:system|model)|(?:ai|llm) "
    r"(?:judge|moderator|classifier)|judge model|moderation (?:model|system|filter|layer)"
    r"|screening (?:model|system|layer))"
)

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
    # Secrets are only flagged when something *asks to disclose* them, so a bare
    # mention of a word like "token" or "password" is no longer a false positive.
    (
        "secret_extraction",
        r"\b(show|reveal|print|display|tell|give|send|leak|expose|share|disclose|dump|output|repeat|provide|list)\b[^.\n]{0,30}\b(api[_\s-]?key|password|passphrase|secret key|secret|credentials?|private key|access key|(?:api|auth|access|bearer|session)[_\s-]?token)s?\b",  # noqa: E501
        "Asks the model to disclose secrets or credentials.",
    ),
    (
        "secret_extraction",
        r"\b(your|the system|the admin|system|admin|root)\b[^.\n]{0,12}\b(api[_\s-]?key|password|passphrase|secret|token|credentials?|access key)s?\b",  # noqa: E501
        "Tries to elicit the system's own secrets or credentials.",
    ),
    (
        "secret_extraction",
        r"\b(show|reveal|print|leak|dump|read|cat|send|expose|exfiltrate|output|paste)\b[^.\n]{0,30}(\.env\b|\benv file|credentials?\.(json|ya?ml)|id_rsa|\.pem\b|private[_\s-]?key)",  # noqa: E501
        "Attempts to read or exfiltrate a secrets / credentials file.",
    ),
    # --- Role-play / persona override -------------------------------------
    (
        "roleplay_override",
        r"\b(you are|act as|pretend to be|roleplay as|imagine you are|from now on you are)\b[^.\n]{0,40}\b(dan|jailbroken|unfiltered|unrestricted|no restrictions|evil|developer mode)\b",  # noqa: E501
        "Tries to put the model into an unrestricted persona (jailbreak).",
    ),
    (
        "roleplay_override",
        r"\bdeveloper mode\b|\bdo anything now\b|(?-i:\bDAN\b)",
        "Invokes a known jailbreak persona ('DAN' / developer mode).",
    ),
    (
        "roleplay_override",
        r"\b(stay in character|never break character|always stay in (their|your|the|his|her) roles?|without (even )?falling out of (the )?(role|character|figure))\b",  # noqa: E501
        "Insists the model never leave an assigned role, a common jailbreak frame.",
    ),
    (
        "roleplay_override",
        r"\b(you are|you're|you will be)\s+(now\s+)?(role-?playing|playing|acting)\s+as\b[^.\n]{0,40}\b(respond|answer|reply)\b[^.\n]{0,30}\b(any|every|all)\b",  # noqa: E501
        "Forces a persona onto every future answer, a goal-hijacking jailbreak frame.",
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
    # --- Judge manipulation: text aimed at the guardrail itself ------------
    (
        "judge_manipulation",
        r"\b(note|message|instructions?|attention|hey|dear)\b[ ,:]{0,3}(?:(?:to|for)\s+)?(?:the\s+|any\s+|all\s+)?" + _GUARD + r"s?\b",  # noqa: E501
        "Addresses the guardrail itself, trying to influence how the text is screened.",
    ),
    (
        "judge_manipulation",
        r"\b" + _GUARD + r"s?\b[ ,:]{0,3}(please\s+)?(ignore|allow|approve|pass|let|skip|whitelist|do not (?:flag|block)|don't (?:flag|block))\b",  # noqa: E501
        "Gives instructions to the guardrail itself.",
    ),
    (
        "judge_manipulation",
        r"\b(classify|mark|label|rate|treat|judge|score)\s+(this|the following|the above)\s+(prompt|input|request|query)\s+(as|is)\s+(safe|benign|harmless|approved|allowed|clean|not (?:malicious|harmful|unsafe))\b",  # noqa: E501
        "Tries to dictate the guardrail's verdict.",
    ),
    (
        "judge_manipulation",
        r"[\"']?(verdict|classification|is_safe|safety_label)[\"']?\s*[:=]\s*[\"']?(safe|unsafe|benign|true|approved)\b",  # noqa: E501
        "Contains a ready-made verdict, as if to pre-empt the guardrail's own answer.",
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

# Light de-obfuscation: collapse the most common leetspeak substitutions so a
# disguised attack ("1gnore", "p4ssw0rd") still matches the rules above. We match
# against both the original and this normalised copy, so normalisation can only
# catch more attacks, never change how a clean prompt reads.
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)


def _deleet(text: str) -> str:
    return text.translate(_LEET)


# Scripts whose presence mid-prompt (when the prompt is mostly Latin) often
# signals a multilingual injection trying to smuggle instructions past an
# English-only filter, the exact blind spot called out in the coursework.
_NON_LATIN = re.compile(
    r"[Ѐ-ӿ]"          # Cyrillic
    r"|[؀-ۿ]"         # Arabic
    r"|[一-鿿]"         # CJK
    r"|[぀-ヿ]"         # Hiragana/Katakana
    r"|[가-힯]"         # Hangul
)

# Injection verbs in a few languages. This is the *blocking* multilingual
# signal: a foreign instruction verb is what separates an actual smuggled
# instruction from innocent foreign text (e.g. a translation question).
_FOREIGN_INJECTION = re.compile(
    r"\b(olvida|ignora|wykonaj|zignoruj|vergiss|ignorier|oublie|игнорир|忘记|無視)\w*\b"
    # Spanish "forget" in any form, but only next to "everything / before / the
    # instructions", so "olvidé mi contraseña" (I forgot my password) stays SAFE.
    r"|\bolvid\w*\b[^.\n]{0,30}\b(todo|anterior|antes|instrucciones)\b",
    re.IGNORECASE,
)


def scan(prompt: str) -> list[HeuristicHit]:
    """Return every heuristic rule that matched ``prompt`` (possibly empty).

    Rules run over the text as written, over a plain copy with common obfuscation
    undone (see normalize.py), and over any hidden content that copy uncovered
    (invisible tag characters, base64). Each also gets a de-leetspeaked pass.
    """

    norm = normalize(prompt)
    candidates = [(prompt, False), (norm.text, False)] + [(h, True) for h in norm.hidden]
    hits: list[HeuristicHit] = []
    for category, regex, reason in _COMPILED:
        for text, hidden in candidates:
            match = regex.search(text) or regex.search(_deleet(text))
            if match:
                pattern = match.group(0).strip()
                hits.append(HeuristicHit(
                    category=category,
                    pattern=f"{pattern} (in hidden content)" if hidden else pattern,
                    reason=reason,
                ))
                break
    hits.extend(HeuristicHit(s.category, s.pattern, s.reason) for s in norm.signals)

    # Multilingual injection: only a foreign *instruction verb* blocks. A prompt
    # that merely mixes scripts (e.g. an innocent translation question) is
    # recorded as a low-confidence signal instead, so it escalates to the LLM
    # judge rather than being blocked outright.
    latin = sum(1 for ch in prompt if ch.isascii() and ch.isalpha())
    mixed_script = latin > 20 and _NON_LATIN.search(prompt) is not None
    if any(_FOREIGN_INJECTION.search(text) for text, _ in candidates):
        hits.append(
            HeuristicHit(
                category="multilingual_injection",
                pattern="foreign instruction verb",
                reason=(
                    "Switches language mid-prompt to issue instructions, a "
                    "technique used to slip past an English-only filter."
                ),
            )
        )
    elif mixed_script:
        hits.append(
            HeuristicHit(
                category="mixed_script",
                pattern="mixed-script text",
                reason=(
                    "Mixes writing scripts mid-prompt; not blocked on its own, "
                    "but flagged for the judge layer to weigh."
                ),
            )
        )
    return hits
