---
title: LLM Blue-Team Guardrail
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
license: mit
app_port: 7860
pinned: false
short_description: Prompt-injection guardrail, guarded RAG and MCP server
---

# Prompt Guardrail

> **An LLM blue-team project: the defensive counterpart to my red-team [Secure AI coursework](https://github.com/daniel-omari/ml-security-redteaming-guardrails).**

A layered guardrail service that screens prompts for injection, jailbreak and
social-engineering attempts before they reach a production LLM. It pairs a fast
heuristic pass with a hosted-LLM judge and returns a fully explainable verdict.
The same guardrail also protects a **RAG pipeline against indirect prompt
injection** (instructions planted in retrieved documents), and is available to
AI agents as an **MCP server**. It ships as a deployable full-stack app (React +
TypeScript frontend, FastAPI backend, PostgreSQL with pgvector, Docker, CI).

[![CI](https://github.com/daniel-omari/llm-blue-team-guardrail/actions/workflows/ci.yml/badge.svg)](https://github.com/daniel-omari/llm-blue-team-guardrail/actions/workflows/ci.yml)

> **Live demo:** https://daniel-omari-llm-blue-team-guardrail.hf.space  
> (free tier, so the first load after it has been idle takes a few seconds to wake).
> Try the **Knowledge base** tab to watch poisoned documents get quarantined.

![Prompt Guardrail screening prompts for injection and jailbreak attempts](docs/demo.gif)

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
   signature, the prompt is blocked and the request short-circuits. The rules
   are precision-tuned: sensitive nouns only match with a disclosure verb
   around them, every rule also runs over a de-leetspeaked copy of the prompt,
   and script-mixing on its own is a low-confidence signal for the judge
   rather than an instant block.

2. **Hosted-LLM judge.** Only the ambiguous prompts that survive the heuristic
   layer are escalated to a small hosted model, which returns a structured
   SAFE/UNSAFE verdict with a confidence score and a one-line reason. The judge
   is provider-agnostic: it speaks both the Anthropic API and the OpenAI-style
   API used by Groq, Google Gemini and others (the live demo runs on Groq's free
   tier), selected by configuration alone. It degrades gracefully: with no API
   key, an outage or a used-up quota the service runs heuristics-only and flags
   the decision as degraded, so the demo stays live with or without credentials.

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

## Guarded RAG: stopping indirect prompt injection

Retrieval-augmented generation has a weak spot: anyone who can get text into the
knowledge base (a vendor document, a wiki edit, a customer ticket) can plant
instructions that the model then reads as if they came from the developer. The
demo knowledge base is a small fictional company wiki ("Halcyon Robotics") where
three pages are poisoned this way, from a blatant "ignore all previous
instructions" to a subtle note asking the assistant to present a fake expense
policy as official and hide the note.

`POST /rag/ask` defends in four steps:

1. **Screen the question** as a prompt (direct injection is blocked up front).
2. **Retrieve** the most similar sections by embedding similarity, using a small
   open model (`BAAI/bge-small-en-v1.5`) that runs locally via ONNX, so search
   needs no API key or GPU.
3. **Screen every retrieved section as a document** before the model sees it.
   Documents get their own judge rubric: they may legitimately talk about
   passwords ("never share your password"), so a credential mention is only a
   signal there, while text that addresses the AI is the threat. Unsafe
   sections are quarantined: reported to the caller, never shown to the model.
4. **Answer from the clean sections only**, with the context wrapped in escaped
   document tags and a system prompt that treats it as data, not instructions.

The response lists every retrieved section with its verdict, who decided it
and whether it was used. Embeddings live in an in-memory index, or in Postgres
with **pgvector** (HNSW index) whenever `DATABASE_URL` points at Postgres, as it
does in docker-compose; CI checks that both stores rank identically.

## MCP server: the guardrail as a tool for AI agents

The guardrail is also an [MCP](https://modelcontextprotocol.io) server (official
Python SDK), so agents such as Claude Desktop or Claude Code can call it before
acting on untrusted text. Three read-only tools, with typed results:

| Tool                    | What it does                                                         |
| ----------------------- | -------------------------------------------------------------------- |
| `classify_prompt`       | Screen one prompt for injection, jailbreaks and goal hijacking        |
| `screen_documents`      | Screen up to 20 texts (web pages, emails, files, tool output) an agent is about to read |
| `search_knowledge_base` | Guarded retrieval: only sections that passed the guardrail come back |

**Locally (stdio).** Add this to Claude Desktop's config (Settings > Developer >
Edit Config), with the paths pointing at your checkout:

```json
{
  "mcpServers": {
    "prompt-guardrail": {
      "command": "C:\\path\\to\\llm-blue-team-guardrail\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp_server"],
      "env": { "PYTHONPATH": "C:\\path\\to\\llm-blue-team-guardrail\\backend" }
    }
  }
}
```

**Remotely (Streamable HTTP).** The API serves the same tools at `/mcp`, so any
MCP client that supports Streamable HTTP can connect to
`https://daniel-omari-llm-blue-team-guardrail.hf.space/mcp`. The endpoint is
stateless and protected against DNS rebinding (it only answers to the host
names in `MCP_ALLOWED_HOSTS`).

## API

| Method | Path        | Description                                                |
| ------ | ----------- | ---------------------------------------------------------- |
| POST   | `/classify` | Screen a single prompt and return a layered verdict         |
| POST   | `/rag/ask`  | Answer from the knowledge base, screening every retrieved section |
| POST   | `/mcp`      | MCP endpoint for AI agents (Streamable HTTP)                |
| GET    | `/history`  | Recent classifications (requires a database)                |
| GET    | `/health`   | Liveness plus which optional features are enabled           |

Interactive API docs are served at `/docs` (FastAPI / OpenAPI).

## Quick start

### With Docker (full stack)

```bash
# optional: enable the LLM judge, e.g. with Groq's free tier
export LLM_API_KEY=...
export LLM_PROVIDER=openai
export LLM_BASE_URL=https://api.groq.com/openai/v1
export LLM_MODEL=openai/gpt-oss-20b
export LLM_REASONING_EFFORT=low

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

Configuration is via environment variables or `backend/.env` (see
`backend/.env.example`). Every external dependency is optional: with no
`DATABASE_URL` history uses a local SQLite file and RAG uses the in-memory
index, and with no `LLM_API_KEY` the service runs heuristics-only and the RAG
demo returns the clean passages instead of a generated answer.

| Variable               | Default                      | Purpose                                            |
| ---------------------- | ---------------------------- | -------------------------------------------------- |
| `LLM_API_KEY`          | none                         | Enables the LLM judge and RAG answers              |
| `LLM_PROVIDER`         | `anthropic`                  | `anthropic` or `openai` (any OpenAI-compatible API) |
| `LLM_BASE_URL`         | the provider's official API  | e.g. `https://api.groq.com/openai/v1`             |
| `LLM_MODEL`            | `claude-haiku-4-5-20251001`  | Model name at that provider                        |
| `LLM_REASONING_EFFORT` | none                         | e.g. `low` for reasoning models                    |
| `DATABASE_URL`         | `sqlite:///./guardrail.db`   | Postgres URL switches history and RAG to Postgres  |
| `RAG_VECTOR_STORE`     | `auto`                       | `auto`, `memory` or `pgvector`                     |
| `MCP_ALLOWED_HOSTS`    | `localhost:*,127.0.0.1:*`    | Host names the `/mcp` endpoint answers to          |

## Tests

```bash
cd backend
pytest -q          # heuristics, judge, RAG, MCP and API tests
ruff check .       # lint
```

The tests never call a real model: the judge and the RAG answerer are tested
against a fake provider, retrieval uses a deterministic stand-in embedder (set
`RAG_REAL_MODEL=1` to also check the real one), and the MCP tools are called
through an in-process MCP client and over HTTP. In CI, a pgvector service
container runs the Postgres vector-store tests, Bandit (SAST) and pip-audit
(SCA) scan the backend, CodeQL and Dependabot watch the repository, and the
frontend is type-checked and built.

## Benchmark

`benchmark/run_benchmark.py` scores the guardrail against labelled SAFE/UNSAFE
cases, treating an attack (UNSAFE) as the positive class and reporting a
confusion matrix per split and overall.

```bash
cd backend
python -m benchmark.run_benchmark                       # prompts
python -m benchmark.run_benchmark --documents           # documents (indirect injection)
python -m benchmark.run_benchmark --documents --pace 2.1   # pace judge calls for a free tier
```

**Prompts** (34 cases): the labelled cases from the SCC353 coursework, which
seeded the heuristic rules, plus a held-out split of fresh prompts that were
not used to write them.

| split      | heuristics only: precision / recall / F1 | full pipeline: precision / recall / F1 / FPR |
| ---------- | ----------------------------------------- | -------------------------------------------- |
| coursework | 100% / 40% / 0.57                          | 89% / 80% / 0.84 / 10%                       |
| held-out   | 100% / 75% / 0.86                          | 100% / 100% / 1.00 / 0%                      |
| overall    | 100% / 56% / 0.71                          | 94% / 89% / 0.91 / 6%                        |

**Documents** (51 cases): every section of the RAG knowledge base (3 of 27
poisoned) plus 24 held-out snippets: benign text that merely mentions passwords
or instructions, and injections in many styles (hidden HTML comments, fake
system tags, exfiltration links and emails, impersonating the developer, tool
calls, CV and peer-review manipulation, Spanish).

| split          | heuristics only: precision / recall / F1 | full pipeline: precision / recall / F1 / FPR |
| -------------- | ----------------------------------------- | -------------------------------------------- |
| knowledge base | 100% / 67% / 0.80                          | 100% / 100% / 1.00 / 0%                      |
| held-out       | 100% / 17% / 0.29                          | 100% / 100% / 1.00 / 0%                      |
| overall        | 100% / 27% / 0.42                          | 100% / 100% / 1.00 / 0%                      |

The heuristic layer is deliberately high-precision: no false alarms, but it
only catches blatant attacks, and almost none of the document-borne ones,
which rarely use the classic phrasings. The LLM judge (here `gpt-oss-20b` on
Groq) recovers that recall. Adding a goal-hijacking clause to the prompt judge's
rubric raised coursework recall from 40% to 80% at the cost of one false alarm.
Honest caveats: these sets are small, the document cases were written for this
project, and LLM-judge figures vary slightly between runs.

## Tech stack

Backend: Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL + pgvector, httpx,
fastembed (ONNX embeddings), the MCP Python SDK.
Frontend: React, TypeScript, Vite.
Infrastructure: Docker, docker-compose, GitHub Actions (with a pgvector service
container, Bandit, pip-audit), CodeQL, Dependabot, Hugging Face Spaces.

## Roadmap

- Rate limiting and API-key auth for the public API and MCP endpoints.
- Larger public benchmarks for indirect injection (e.g. BIPIA) and jailbreaks.
- Per-category policy thresholds, and an analytics dashboard over `/history`.
- Screen documents once at ingestion time for large knowledge bases, storing the
  verdict next to the embedding.

## License

MIT, see [LICENSE](LICENSE).
