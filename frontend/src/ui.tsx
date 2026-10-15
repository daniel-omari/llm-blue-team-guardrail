// Small pieces shared by both tabs.

// Map internal layer / decision identifiers to friendly display labels, so a
// benign result reads "heuristic layer" rather than "heuristics_degraded".
const LABELS: Record<string, string> = {
  heuristics: "heuristic layer",
  heuristics_degraded: "heuristic layer",
  llm_judge: "LLM judge",
};
export const prettyLabel = (id: string): string => LABELS[id] ?? id;

// Coloured SAFE / UNSAFE / SKIPPED status pill.
export function Badge({ verdict }: { verdict: string }) {
  const cls = verdict === "UNSAFE" ? "badge unsafe" : verdict === "SAFE" ? "badge safe" : "badge skip";
  return <span className={cls}>{verdict}</span>;
}
