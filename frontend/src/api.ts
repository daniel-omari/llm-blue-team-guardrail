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
