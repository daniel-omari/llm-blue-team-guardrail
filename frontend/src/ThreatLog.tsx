import { useState } from "react";
import { Badge } from "./ui";

// The visitor's own checks, kept only in this browser (localStorage). Nothing here is
// sent anywhere or shown to anyone else.

export type Mode = "prompt" | "rag";

export interface LogEntry {
  id: string;
  at: number; // epoch ms
  mode: Mode;
  verdict: "SAFE" | "UNSAFE";
  by: string; // who decided, or a short summary for knowledge-base questions
  path: "heuristics" | "judge" | "rag"; // which route the check took, for the timing stats
  text: string;
  ms: number;
}

const KEY = "guardrail.threatlog.v1";
const MAX_ENTRIES = 50;
const MAX_TEXT = 280;

// Storage can hold anything (an older version, a hand edit, another app on the same
// origin), so only well-formed entries are kept; anything else is dropped, not rendered.
function isEntry(e: unknown): e is LogEntry {
  if (typeof e !== "object" || e === null) return false;
  const x = e as Record<string, unknown>;
  return (
    typeof x.id === "string" &&
    typeof x.at === "number" &&
    (x.mode === "prompt" || x.mode === "rag") &&
    (x.verdict === "SAFE" || x.verdict === "UNSAFE") &&
    typeof x.by === "string" &&
    (x.path === "heuristics" || x.path === "judge" || x.path === "rag") &&
    typeof x.text === "string" &&
    typeof x.ms === "number"
  );
}

export function loadLog(): LogEntry[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(isEntry)
      .slice(0, MAX_ENTRIES)
      .map((e) => (e.text.length > MAX_TEXT ? { ...e, text: `${e.text.slice(0, MAX_TEXT)}...` } : e));
  } catch {
    return []; // storage blocked or corrupted: start empty
  }
}

// The storage key, so other tabs' changes can be picked up (see App).
export const LOG_KEY = KEY;

export function saveLog(entries: LogEntry[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries));
  } catch {
    /* storage full or unavailable: the log still works for this visit */
  }
}

// Newest first, capped, with long inputs trimmed so storage stays small.
export function addEntry(entries: LogEntry[], e: Omit<LogEntry, "id" | "at">): LogEntry[] {
  const text = e.text.length > MAX_TEXT ? `${e.text.slice(0, MAX_TEXT)}...` : e.text;
  const entry: LogEntry = { ...e, text, id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, at: Date.now() };
  return [entry, ...entries].slice(0, MAX_ENTRIES);
}

// Today's checks show the time; older ones add the date so a long-lived log stays clear.
function clock(at: number): string {
  const d = new Date(at);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  if (d.toDateString() === new Date().toDateString()) return time;
  return `${d.toLocaleDateString([], { day: "numeric", month: "short" })} ${time}`;
}

// Side panel listing the checks. Clicking one loads it back into its mode's input.
export default function ThreatLog(props: {
  entries: LogEntry[];
  onPick: (e: LogEntry) => void;
  onClear: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const { entries } = props;

  return (
    <aside className="feed hudbox" aria-label="Threat log">
      <div className="feed-head">
        <h3>
          <i aria-hidden="true" />
          THREAT LOG
        </h3>
        {entries.length > 0 &&
          (confirming ? (
            <span className="feed-confirm">
              clear all?
              <button onClick={() => { props.onClear(); setConfirming(false); }}>yes</button>
              <button onClick={() => setConfirming(false)}>no</button>
            </span>
          ) : (
            <button className="feed-clear" onClick={() => setConfirming(true)}>clear</button>
          ))}
      </div>
      <p className="feed-note">
        Your checks only, saved in this browser{entries.length > 0 && ` (last ${MAX_ENTRIES} kept)`}.
      </p>

      {entries.length === 0 ? (
        <p className="feed-empty">Nothing yet. Pick a sample attack and screen it.</p>
      ) : (
        <ol className="feed-list">
          {entries.map((e) => (
            <li key={e.id}>
              <button className="item" onClick={() => props.onPick(e)} title="Load this into the input again">
                <span className="item-meta">
                  <Badge verdict={e.verdict} />
                  <span>
                    {clock(e.at)} &middot; {e.mode === "rag" ? "kb" : "prompt"} &middot; {e.by}
                  </span>
                </span>
                <span className="item-text">{e.text}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
