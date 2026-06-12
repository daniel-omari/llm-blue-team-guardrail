"""Benchmark the guardrail against labelled SAFE/UNSAFE prompts.

UNSAFE (an attack) is treated as the positive class. The harness reports a
confusion matrix with accuracy, precision, recall, F1 and false-positive rate,
per data split and overall, then lists every misclassified prompt.

The dataset (cases.json) is seeded from the labelled cases in the SCC353 Secure
AI coursework, plus a held-out split of fresh prompts that were not used when
writing the heuristic rules, so the held-out figures estimate generalisation.

Run from the backend directory:

    python -m benchmark.run_benchmark

With no LLM_API_KEY set the service runs heuristics-only, so the figures measure
the fast first layer on its own. Set LLM_API_KEY to benchmark the full pipeline.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from dataclasses import dataclass

# Allow running as a plain script as well as `python -m benchmark.run_benchmark`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.guardrail import engine  # noqa: E402

DATA_PATH = pathlib.Path(__file__).parent / "cases.json"
POSITIVE = "UNSAFE"


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


@dataclass
class Metrics:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float:
        return _safe_div(self.tp + self.tn, self.total)

    @property
    def precision(self) -> float:
        return _safe_div(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float:
        return _safe_div(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return _safe_div(2 * p * r, p + r)

    @property
    def false_positive_rate(self) -> float:
        return _safe_div(self.fp, self.fp + self.tn)


def compute_metrics(pairs: list[tuple[str, str]]) -> Metrics:
    """Tally a confusion matrix from (true_label, predicted_label) pairs."""
    m = Metrics()
    for true, pred in pairs:
        if true == POSITIVE and pred == POSITIVE:
            m.tp += 1
        elif true == POSITIVE:
            m.fn += 1
        elif pred == POSITIVE:
            m.fp += 1
        else:
            m.tn += 1
    return m


async def evaluate(cases: dict) -> tuple[list[dict], bool]:
    """Run every prompt through the guardrail and collect per-case records."""
    records: list[dict] = []
    judge_ran = False
    for split, labels in cases.items():
        for true_label, prompts in labels.items():
            for prompt in prompts:
                result = await engine.classify(prompt)
                if result["decided_by"] == "llm_judge":
                    judge_ran = True
                records.append({
                    "split": split,
                    "true": true_label,
                    "pred": result["verdict"],
                    "prompt": prompt,
                })
    return records, judge_ran


def _format(m: Metrics) -> str:
    return (
        f"  accuracy={m.accuracy:.1%}  precision={m.precision:.1%}  "
        f"recall={m.recall:.1%}  F1={m.f1:.2f}  FPR={m.false_positive_rate:.1%}\n"
        f"  (TP={m.tp}  FP={m.fp}  TN={m.tn}  FN={m.fn})"
    )


def report(records: list[dict], judge_ran: bool) -> None:
    mode = "full pipeline (heuristics + LLM judge)" if judge_ran else \
        "heuristics-only (no LLM_API_KEY set)"
    print("=" * 72)
    print("PROMPT GUARDRAIL BENCHMARK")
    print(f"mode: {mode}")
    print("=" * 72)

    for split in sorted({r["split"] for r in records}):
        pairs = [(r["true"], r["pred"]) for r in records if r["split"] == split]
        print(f"\n[{split}]  n={len(pairs)}")
        print(_format(compute_metrics(pairs)))

    overall = [(r["true"], r["pred"]) for r in records]
    print(f"\n[overall]  n={len(overall)}")
    print(_format(compute_metrics(overall)))

    misses = [r for r in records if r["true"] != r["pred"]]
    if misses:
        print("\nmisclassified:")
        for r in misses:
            kind = "missed attack (FN)" if r["true"] == POSITIVE else "false alarm (FP)"
            print(f"  [{kind}] ({r['split']}) {r['prompt'][:88]}")
    print()


async def main() -> None:
    cases = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records, judge_ran = await evaluate(cases)
    report(records, judge_ran)


if __name__ == "__main__":
    asyncio.run(main())
