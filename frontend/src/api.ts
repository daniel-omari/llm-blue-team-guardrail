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
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json();
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
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json();
}
