// Thin client for the guardrail API.

export interface LayerResult {
  name: string;
  ran: boolean;
  verdict: string;
  confidence?: number | null;
  reason?: string | null;
  findings?: { category: string; pattern: string; reason: string }[] | null;
}

export interface ClassifyResponse {
  verdict: "SAFE" | "UNSAFE";
  confidence: number;
  reason: string;
  decided_by: string;
  latency_ms: number;
  layers: LayerResult[];
}

// In dev, requests go through Vite's proxy at /api. In production, set
// VITE_API_BASE to the deployed backend URL at build time.
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

// Send a prompt to the guardrail API and return its verdict (throws on error).
export async function classifyPrompt(prompt: string): Promise<ClassifyResponse> {
  const res = await fetch(`${API_BASE}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

// A readable error: the rate limit gets a plain sentence, anything else the status.
async function errorMessage(res: Response): Promise<string> {
  if (res.status === 429) {
    const wait = res.headers.get("Retry-After");
    return `Slow down a little: too many checks in a short time. Try again in ${wait ?? "a few"} seconds.`;
  }
  return `API error ${res.status}: ${await res.text()}`;
}

// ---- Knowledge base (guarded RAG) ----

export interface RagChunk {
  id: string;
  title: string;
  section: string;
  source: string;
  text: string;
  score: number;
  verdict: "SAFE" | "UNSAFE";
  decided_by: string;
  reason: string;
  used: boolean;
}

export interface RagResponse {
  question: string;
  answer: string;
  answer_mode: "llm" | "passages" | "no_context" | "blocked";
  question_screening: ClassifyResponse;
  chunks: RagChunk[];
  quarantined: number;
  latency_ms: number;
}

// Ask the knowledge base a question; every retrieved chunk is screened server-side.
export async function askKnowledgeBase(question: string): Promise<RagResponse> {
  const res = await fetch(`${API_BASE}/rag/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

// ---- Aggregate stats (all visitors, counts and timings only) ----

export interface Stats {
  total: number;
  blocked: number;
  allowed: number;
  heuristics_avg_ms: number | null;
  judge_avg_ms: number | null;
}

// Fetch the server-wide numbers; resolves to null when the server has no database.
export async function fetchStats(): Promise<Stats | null> {
  try {
    const res = await fetch(`${API_BASE}/stats`);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}
