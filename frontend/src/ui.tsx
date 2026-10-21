import { useEffect, useState, type MouseEvent, type ReactNode } from "react";

// Small pieces shared by both modes.

// Map internal layer / decision identifiers to friendly display labels, so a
// benign result reads "heuristic layer" rather than "heuristics_degraded".
const LABELS: Record<string, string> = {
  heuristics: "heuristic layer",
  heuristics_degraded: "heuristic layer",
  llm_judge: "LLM judge",
};
export const prettyLabel = (id: string): string => LABELS[id] ?? id;

// Text to load into an input (e.g. picked from the threat log). The nonce makes
// picking the same entry twice still count as a new request.
export interface Load {
  text: string;
  nonce: number;
}

// Coloured SAFE / UNSAFE / SKIPPED status tag.
export function Badge({ verdict, big = false }: { verdict: string; big?: boolean }) {
  const kind = verdict === "UNSAFE" ? "u" : verdict === "SAFE" ? "s" : "k";
  const icon = verdict === "UNSAFE" ? "✕ " : verdict === "SAFE" ? "✓ " : "";
  return (
    <span className={`tag ${kind}${big ? " big" : ""}`}>
      {icon}
      {verdict}
    </span>
  );
}

const calm = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// A burst of small pixel sparks at the click point, in the theme's accent colours.
function sparks(e: MouseEvent<HTMLButtonElement>) {
  if (calm() || e.clientX === 0) return; // skip for keyboard "clicks" and reduced motion
  const css = getComputedStyle(document.documentElement);
  const colours = ["--accent-hi", "--mint", "--lilac"].map((v) => css.getPropertyValue(v));
  for (let i = 0; i < 10; i++) {
    const s = document.createElement("i");
    const angle = (i / 10) * Math.PI * 2;
    const r = 22 + Math.random() * 18;
    s.className = "spark";
    s.style.left = `${e.clientX}px`;
    s.style.top = `${e.clientY}px`;
    s.style.background = colours[i % 3];
    s.style.setProperty("--dx", `${Math.cos(angle) * r}px`);
    s.style.setProperty("--dy", `${Math.sin(angle) * r}px`);
    document.body.appendChild(s);
    window.setTimeout(() => s.remove(), 500);
  }
}

// The main call-to-action button: lifts on hover, RGB-split label, sparks on click.
export function ActionButton(props: { onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      className="btn"
      disabled={props.disabled}
      onClick={(e) => {
        sparks(e);
        props.onClick();
      }}
    >
      <span className="label">{props.children}</span>
    </button>
  );
}

type Theme = "night" | "day";

function readTheme(): Theme {
  const t = document.documentElement.dataset.theme;
  return t === "day" ? "day" : "night";
}

// Night / day switch. The choice is remembered in this browser only.
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* storage can be unavailable (private mode); the toggle still works */
    }
  }, [theme]);
  const next: Theme = theme === "night" ? "day" : "night";
  return (
    <button className="toggle" onClick={() => setTheme(next)} aria-label={`Switch to ${next} theme`}>
      {theme === "night" ? "☾ night" : "☀ day"}
    </button>
  );
}
