"""Benchmark the guardrail against labelled SAFE/UNSAFE prompts or documents.

UNSAFE (an attack) is treated as the positive class. The harness reports a
confusion matrix with accuracy, precision, recall, F1 and false-positive rate,
per data split and overall, then lists every misclassified prompt.

The dataset (cases.json) is seeded from the labelled cases in the SCC353 Secure
AI coursework, plus a held-out split of fresh prompts that were not used when
writing the heuristic rules, so the held-out figures estimate generalisation.

With --documents it scores the document mode instead (indirect prompt injection
in retrieved text): every chunk of the RAG knowledge base, labelled by which pages
were deliberately poisoned, plus a held-out set of document snippets
(document_cases.json) with benign text that merely mentions passwords or
instructions, and injections in many styles (hidden comments, fake system tags,
exfiltration links, tool calls, CV and peer-review manipulation).

With --judge-attacks it scores judge_attacks.json: prompts written to manipulate the
guardrail itself (fake approvals, "you're just a filter", ready-made verdicts, tag
breakouts) next to benign controls that look alike, including pairs that differ only
in the manipulation, so a pass means the judge reacts to the trick, not the topic.

--repeat N runs every case N times and reports verdict stability (the share of
cases that got the same verdict every time), and --temperature / --effort override
the model settings, so judge configurations can be compared on data.

Run from the backend directory:

    python -m benchmark.run_benchmark
    python -m benchmark.run_benchmark --documents
    python -m benchmark.run_benchmark --judge-attacks --repeat 3 --pace 2.1

With no LLM_API_KEY set the service runs heuristics-only, so the figures measure
the fast first layer on its own. Set LLM_API_KEY to benchmark the full pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from dataclasses import dataclass

# Allow running as a plain script as well as `python -m benchmark.run_benchmark`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.guardrail import engine  # noqa: E402
from app.rag.documents import load_corpus  # noqa: E402

DATA_PATH = pathlib.Path(__file__).parent / "cases.json"
DOCUMENT_DATA_PATH = pathlib.Path(__file__).parent / "document_cases.json"
JUDGE_DATA_PATH = pathlib.Path(__file__).parent / "judge_cases.json"
JUDGE_PATHS = {"llm_judge", "judge_integrity"}
# The knowledge-base chunks that carry a planted injection (see rag/corpus/README.md)
POISONED_CHUNKS = {"vendor-onboarding#2", "wiki-community-tips#2", "support-ticket-4471#2"}
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


def document_cases() -> dict:
    """The knowledge base (labelled by its poisoned chunks) plus the held-out snippets."""
    corpus: dict[str, list[str]] = {"SAFE": [], "UNSAFE": []}
    for chunk in load_corpus():
        corpus["UNSAFE" if chunk.id in POISONED_CHUNKS else "SAFE"].append(chunk.text)
    held_out = json.loads(DOCUMENT_DATA_PATH.read_text(encoding="utf-8"))
    return {"knowledge_base": corpus, **held_out}


async def evaluate(cases: dict, source: str = "prompt", pace: float = 0.0,
                   repeat: int = 1) -> tuple[list[dict], bool]:
    """Run every case through the guardrail ``repeat`` times; one record per run.

    ``pace`` waits that many seconds after each case that reached the LLM judge, to
    stay under a free tier's rate limit (e.g. 2.1 for Groq's 30 requests a minute).
    """
    records: list[dict] = []
    judge_ran = False
    for run in range(repeat):
        for split, labels in cases.items():
            for true_label, prompts in labels.items():
                for prompt in prompts:
                    result = await engine.classify(prompt, source=source)
                    if result["decided_by"] in JUDGE_PATHS:
                        judge_ran = True
                    if pace and result["decided_by"] != "heuristics":
                        await asyncio.sleep(pace)
                    records.append({
                        "run": run,
                        "split": split,
                        "true": true_label,
                        "pred": result["verdict"],
                        "decided_by": result["decided_by"],
                        "prompt": prompt,
                    })
    return records, judge_ran


def stability(records: list[dict]) -> tuple[float, list[tuple[str, int, int]]]:
    """Share of cases whose verdict was identical on every run, plus the unstable
    ones as (prompt, times UNSAFE, runs)."""
    verdicts: dict[str, list[str]] = {}
    for r in records:
        verdicts.setdefault(r["prompt"], []).append(r["pred"])
    unstable = [(p, v.count(POSITIVE), len(v)) for p, v in verdicts.items() if len(set(v)) > 1]
    return _safe_div(len(verdicts) - len(unstable), len(verdicts)), unstable


def _format(m: Metrics) -> str:
    return (
        f"  accuracy={m.accuracy:.1%}  precision={m.precision:.1%}  "
        f"recall={m.recall:.1%}  F1={m.f1:.2f}  FPR={m.false_positive_rate:.1%}\n"
        f"  (TP={m.tp}  FP={m.fp}  TN={m.tn}  FN={m.fn})"
    )


def report(records: list[dict], judge_ran: bool, source: str = "prompt") -> None:
    mode = "full pipeline (heuristics + LLM judge)" if judge_ran else \
        "heuristics-only (no LLM_API_KEY set)"
    runs = len({r.get("run", 0) for r in records})
    print("=" * 72)
    print(f"PROMPT GUARDRAIL BENCHMARK ({source}s)")
    print(f"mode: {mode}")
    if judge_ran:
        print(f"judge: {settings.llm_model}  temperature={settings.llm_temperature or 'default'}"
              f"  reasoning_effort={settings.llm_reasoning_effort or 'default'}")
    if runs > 1:
        print(f"runs: {runs} (figures pool every run)")
    print("=" * 72)

    for split in sorted({r["split"] for r in records}):
        pairs = [(r["true"], r["pred"]) for r in records if r["split"] == split]
        print(f"\n[{split}]  n={len(pairs)}")
        print(_format(compute_metrics(pairs)))

    overall = [(r["true"], r["pred"]) for r in records]
    print(f"\n[overall]  n={len(overall)}")
    print(_format(compute_metrics(overall)))

    degraded = sum(r["decided_by"] == "heuristics_degraded" for r in records)
    if judge_ran and degraded:
        print(f"\nwarning: the LLM judge was unavailable for {degraded} case(s) "
              "(rate limit?); rerun with a larger --pace for clean figures.")

    integrity = sum(r["decided_by"] == "judge_integrity" for r in records)
    if integrity:
        print(f"\njudge integrity check failed on {integrity} case(s) (blocked as UNSAFE).")

    if runs > 1:
        stable, unstable = stability(records)
        print(f"\nverdict stability: {stable:.1%} of cases got the same verdict on all {runs} runs")
        for prompt, unsafe, total in unstable:
            print(f"  UNSAFE {unsafe}/{total}: {prompt[:80]}")

    misses = {(r["true"], r["split"], r["prompt"]) for r in records if r["true"] != r["pred"]}
    if misses:
        print("\nmisclassified (on at least one run):")
        for true, split, prompt in sorted(misses):
            kind = "missed attack (FN)" if true == POSITIVE else "false alarm (FP)"
            print(f"  [{kind}] ({split}) {prompt[:88]}")
    print()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--documents", action="store_true",
                        help="score document screening (indirect injection) instead of prompts")
    parser.add_argument("--judge-attacks", action="store_true",
                        help="score prompts written to manipulate the guardrail itself")
    parser.add_argument("--pace", type=float, default=0.0, metavar="SECONDS",
                        help="pause after each judged case, to respect API rate limits")
    parser.add_argument("--repeat", type=int, default=1, metavar="N",
                        help="run every case N times and report verdict stability")
    parser.add_argument("--temperature", type=float, default=None,
                        help="override LLM_TEMPERATURE for this run")
    parser.add_argument("--effort", default=None, metavar="LEVEL",
                        help="override LLM_REASONING_EFFORT for this run (e.g. low, medium)")
    args = parser.parse_args()

    if args.temperature is not None:
        settings.llm_temperature = args.temperature
    if args.effort is not None:
        settings.llm_reasoning_effort = args.effort
    if args.documents:
        cases, source = document_cases(), "document"
    elif args.judge_attacks:
        cases, source = json.loads(JUDGE_DATA_PATH.read_text(encoding="utf-8")), "prompt"
    else:
        cases, source = json.loads(DATA_PATH.read_text(encoding="utf-8")), "prompt"
    records, judge_ran = await evaluate(cases, source, args.pace, max(1, args.repeat))
    report(records, judge_ran, source)


if __name__ == "__main__":
    asyncio.run(main())
