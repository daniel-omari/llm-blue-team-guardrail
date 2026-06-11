"""Guardrail orchestration: combine the heuristic and LLM layers into one verdict.

Decision policy (defence in depth):

1. Run the fast heuristic layer first.
2. If heuristics find a high-confidence injection signature, the prompt is
   UNSAFE and we short-circuit -- no model call needed.
3. Otherwise escalate to the LLM judge for the ambiguous middle ground.
4. If the judge is unavailable (no key / outage), fall back to "heuristics say
   nothing, so treat as SAFE" -- but the response records that it was a
   degraded, heuristics-only decision so the caller knows.

The response is fully explainable: it reports the final verdict, which layers
ran, what each found, and the end-to-end latency.
"""

from __future__ import annotations

import time
from dataclasses import asdict

from app.guardrail import heuristics, llm_judge

# Categories we trust enough to block on the heuristic layer alone.
_BLOCK_ON_SIGHT = {
    "instruction_override",
    "prompt_extraction",
    "secret_extraction",
    "roleplay_override",
    "multilingual_injection",
}


async def classify(prompt: str) -> dict:
    started = time.perf_counter()

    hits = heuristics.scan(prompt)
    hit_categories = {h.category for h in hits}
    heuristic_block = bool(hit_categories & _BLOCK_ON_SIGHT)

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
                        "reason": "Heuristic layer already blocked the prompt."})
    else:
        judged = await llm_judge.judge(prompt)
        layers.append({
            "name": "llm_judge",
            "ran": judged.available,
            "verdict": judged.verdict,
            "confidence": judged.confidence,
            "reason": judged.reason,
        })
        if judged.available:
            verdict = judged.verdict
            confidence = judged.confidence
            reason = judged.reason
            decided_by = "llm_judge"
        else:
            # Degraded mode: nothing tripped the heuristics and we cannot reach
            # the model, so we allow the prompt but flag the degradation.
            verdict = "SAFE"
            confidence = 0.5
            reason = "No injection signatures detected (heuristics-only, judge unavailable)."
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
