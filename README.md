---
title: LLM Blue-Team Guardrail
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: A layered guardrail that screens prompts for injection and jailbreak attempts.
---

# Prompt Guardrail

> **An LLM blue-team project: the defensive counterpart to my red-team [Secure AI coursework](https://github.com/daniel-omari/ml-security-redteaming-guardrails).**

A layered guardrail service that screens prompts for injection, jailbreak and
social-engineering attempts before they reach a production LLM. It pairs a fast
heuristic pass with a hosted-LLM judge, returns a fully explainable verdict, and
ships as a deployable full-stack app (React + TypeScript frontend, FastAPI
backend, PostgreSQL, Docker, CI).

[![CI](https://github.com/daniel-omari/llm-blue-team-guardrail/actions/workflows/ci.yml/badge.svg)](https://github.com/daniel-omari/llm-blue-team-guardrail/actions/workflows/ci.yml)

> Live demo: _add your deploy URL here_

## Background

This project grew out of the guardrail component of my SCC353 Secure AI
coursework at Lancaster University
([ml-security-redteaming-guardrails](https://github.com/daniel-omari/ml-security-redteaming-guardrails)),
where I red-teamed an LLM and built a single-model SAFE/UNSAFE classifier to
defend it. That classifier worked in a notebook but was not something you could
run, deploy or call. Prompt Guardrail is the productized version: the same
defensive idea, rebuilt as a real service with a fast detection layer in front
of the model, an explainable API, request logging and a UI.

Put simply, the coursework was the red team (finding ways to break a model); this is the blue team (building the defence that stops them). The two are meant to be read as a pair.

## How it works

Incoming prompts pass through two layers, cheapest first (defence in depth):

1. **Heuristic layer.** Compiled regex signatures for known attack families:
   instruction override ("ignore all previous instructions"), system-prompt and
   secret extraction, jailbreak personas (DAN / developer mode), urgency-based
   social engineering, output-format hijacking, and mid-prompt multilingual
   injection. This runs in well under a millisecond and catches the obvious
   attacks without spending an API call. If it finds a high-confidence
   signature, the prompt is blocked and the request short-circuits.

2. **Hosted-LLM judge.** Only the ambiguous prompts that survive the heuristic
   layer are escalated to a small hosted model, which returns a structured
   SAFE/UNSAFE verdict with a confidence score and a one-line reason. The judge
   is provider-agnostic over HTTP and degrades gracefully: with no API key
   configured the service runs heuristics-only and flags the decision as
   degraded, so the demo stays live with or without credentials.

Every response is explainable. It reports the final verdict, which layer decided
it, what each layer found, and the end-to-end latency:

```json
{
  "verdict": "UNSAFE",
  "confidence": 0.95,
  "reason": "Attempts to make the model ignore its previous instructions.",
  "decided_by": "heuristics",
  "latency_ms": 0.21,
  "layers": [
    {
      "name": "heuristics",
      "ran": true,
      "verdict": "UNSAFE",
      "findings": [
        {
          "category": "instruction_override",
          "pattern": "Ignore all previous instructions",
          "reason": "Attempts to make the model ignore its previous instructions."
        }
      ]
    },
    { "name": "llm_judge", "ran": false, "verdict": "SKIPPED" }
  ]
}
```

## API

| Method | Path        | Description                                        |
| ------ | ----------- | -------------------------------------------------- |
| POST   | `/classify` | Screen a single prompt and return a layered verdict |
| GET    | `/history`  | Recent classifications (requires a database)        |
| GET    | `/health`   | Liveness plus which optional features are enabled   |

Interactive API docs are served at `/docs` (FastAPI / OpenAPI).

## Quick start

### With Docker (full stack)

```bash
# optional: enable the LLM judge
export LLM_API_KEY=sk-...

docker compose up --build
# frontend: http://localhost:8080
# API:      http://localhost:8000/docs
```

### Local development

Backend:

```bash
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # http://localhost:8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173 (proxies /api -> :8000)
```

Configuration is via environment variables (see `backend/.env.example`). Every
external dependency is optional: with no `DATABASE_URL` request logging is
skipped, and with no `LLM_API_KEY` the service runs heuristics-only.

## Tests

```bash
cd backend
pytest -q          # unit tests for the heuristic layer + API integration tests
ruff check .       # lint
```

The frontend is type-checked and built in CI (`npm run lint && npm run build`).

## Benchmark

`benchmark/run_benchmark.py` scores the guardrail against labelled SAFE/UNSAFE
prompts, treating an attack (UNSAFE) as the positive class and reporting a
confusion matrix per split and overall. The dataset combines the labelled cases
from the SCC353 Secure AI coursework with a held-out split of fresh prompts that
were not used to write the heuristic rules, so the held-out figures estimate
generalisation.

```bash
cd backend
python -m benchmark.run_benchmark
```

Heuristics-only baseline (no LLM judge), 34 cases:

| split      | precision | recall | F1   | false-positive rate |
| ---------- | --------- | ------ | ---- | ------------------- |
| coursework | 100%      | 40%    | 0.57 | 0%                  |
| held-out   | 100%      | 75%    | 0.86 | 0%                  |
| overall    | 100%      | 56%    | 0.71 | 0%                  |

The fast heuristic layer is deliberately high-precision: it raises zero false
alarms on benign prompts, but on its own catches only the blatant attacks. The
subtle, multilingual and encoded injections it misses are exactly the cases the
design escalates to the LLM judge. Set `LLM_API_KEY` to benchmark the full
pipeline, which is expected to recover most of that recall.

## Tech stack

Backend: Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, httpx.
Frontend: React, TypeScript, Vite.
Infrastructure: Docker, docker-compose, GitHub Actions.

## Roadmap

- Persisted analytics dashboard over the `/history` data.
- Configurable policy thresholds per attack category.
- Tune the heuristic layer to lift recall on the multilingual and role-play
  attacks surfaced by the benchmark.
- Expand the benchmark with public jailbreak datasets and a full-pipeline run.
- Rate limiting and an API-key auth layer for multi-tenant use.

## License

MIT, see [LICENSE](LICENSE).
