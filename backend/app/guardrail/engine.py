"""Guardrail orchestration: combine the heuristic and LLM layers into one verdict.

Decision policy (defence in depth):

1. Run the fast heuristic layer first.
2. If heuristics find a high-confidence injection signature, the prompt is
   UNSAFE and we short-circuit, so no model call is needed.
3. Otherwise escalate to the LLM judge for the ambiguous middle ground.
4. If the judge replies but the reply fails its integrity checks (malformed, off
   schema, wrong canary), the text is UNSAFE: an attacker must not be able to turn
   a confused judge into an "allow". Decided by ``judge_integrity``.
5. If no judge is configured, fall back to "heuristics say nothing, so treat as
   SAFE", recorded as a degraded, heuristics-only decision (``heuristics_degraded``).
6. If a configured judge cannot be reached (outage, timeout, rate limit), follow
   ``JUDGE_FAILURE_MODE``: "open" behaves like 5, "closed" blocks the text
   (``fail_closed``).

The response is fully explainable: it reports the final verdict, which layers
ran, what each found, and the end-to-end latency.

The same pipeline screens two kinds of text. A *prompt* is what a user types. A
*document* is text retrieved for an LLM to read (the RAG knowledge base), where
the threat is indirect prompt injection: instructions planted in the content.
Documents legitimately talk about passwords and credentials ("never share your
password"), so for them a credential mention is only a signal for the judge,
not a block on sight.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Literal

from app.config import settings
from app.guardrail import heuristics, llm_judge
from app.guardrail.normalize import normalize

Source = Literal["prompt", "document"]

# Categories we trust enough to block on the heuristic layer alone, per source.
_BLOCK_ON_SIGHT: dict[Source, set[str]] = {
    "prompt": {
        "instruction_override",
        "prompt_extraction",
        "secret_extraction",
        "roleplay_override",
        "multilingual_injection",
        "judge_manipulation",
        "unicode_smuggling",
    },
    "document": {
        "instruction_override",
        "prompt_extraction",
        "roleplay_override",
        "multilingual_injection",
        "judge_manipulation",
        "unicode_smuggling",
    },
}


def _for_judge(text: str) -> str:
    """The text as sent, plus any hidden content the normaliser decoded, so the judge
    sees what a model reading the raw text would understand."""
    hidden = normalize(text).hidden
    if not hidden:
        return text
    return (text + "\n\n[Hidden content decoded by the guardrail (invisible characters "
            "or base64):]\n" + "\n".join(hidden))


async def classify(text: str, source: Source = "prompt") -> dict:
    """Run text through both layers and return the combined, explainable verdict."""
    started = time.perf_counter()

    hits = heuristics.scan(text)
    hit_categories = {h.category for h in hits}
    heuristic_block = bool(hit_categories & _BLOCK_ON_SIGHT[source])

    layers: list[dict] = [
        {
            "name": "heuristics",
            "ran": True,
            "verdict": "UNSAFE" if heuristic_block else "SAFE",
            "findings": [asdict(h) for h in hits],
        }
    ]

    if heuristic_block:
        verdict = "UNSAFE"
        confidence = 0.95
        reason = hits[0].reason
        decided_by = "heuristics"
        layers.append({"name": "llm_judge", "ran": False, "verdict": "SKIPPED",
                        "reason": f"Heuristic layer already blocked the {source}."})
    else:
        judged = await llm_judge.judge(_for_judge(text), source)
        invalid = judged.status == "invalid"
        layers.append({
            "name": "llm_judge",
            "ran": judged.available or invalid,     # an invalid reply still means it ran
            "verdict": "INVALID" if invalid else judged.verdict,
            "confidence": judged.confidence,
            "reason": judged.reason,
        })
        if judged.available:
            verdict = judged.verdict
            confidence = judged.confidence
            reason = judged.reason
            decided_by = "llm_judge"
        elif judged.status == "invalid":
            verdict = "UNSAFE"
            confidence = 0.8
            reason = ("The judge's reply failed its integrity check, a sign the text "
                      "may be trying to manipulate the judge.")
            decided_by = "judge_integrity"
        elif judged.status == "unavailable" and settings.judge_failure_mode == "closed":
            verdict = "UNSAFE"
            confidence = 0.5
            reason = "The LLM judge could not be reached, so the text was blocked (fail-closed)."
            decided_by = "fail_closed"
        else:
            # Degraded mode: nothing tripped the heuristics and we cannot reach
            # the model, so we allow the prompt but flag the degradation.
            verdict = "SAFE"
            confidence = 0.5
            reason = (
                "No injection signatures detected (heuristics-only, judge unavailable)."
                if not hits
                else "Only low-confidence signals found; allowed "
                "(heuristics-only, judge unavailable)."
            )
            decided_by = "heuristics_degraded"

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "decided_by": decided_by,
        "latency_ms": latency_ms,
        "layers": layers,
    }
