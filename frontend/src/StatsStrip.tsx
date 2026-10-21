import type { Stats } from "./api";
import type { LogEntry } from "./ThreatLog";

const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

// Same numbers as the server's /stats, worked out from this browser's own log.
// Used when the server has no database, so the strip is never empty.
function localStats(entries: LogEntry[]): Stats {
  const prompts = entries.filter((e) => e.mode === "prompt");
  const blocked = prompts.filter((e) => e.verdict === "UNSAFE").length;
  return {
    total: prompts.length,
    blocked,
    allowed: prompts.length - blocked,
    heuristics_avg_ms: avg(prompts.filter((e) => e.path === "heuristics").map((e) => e.ms)),
    judge_avg_ms: avg(prompts.filter((e) => e.path === "judge").map((e) => e.ms)),
  };
}

function ms(v: number | null) {
  if (v === null) return <>--</>;
  const text = v < 10 ? v.toFixed(1) : Math.round(v).toString();
  return (
    <>
      {text}
      <small>ms</small>
    </>
  );
}

// Four live numbers above the console: blocked, allowed, and how fast each layer is.
export default function StatsStrip({ server, entries }: { server: Stats | null; entries: LogEntry[] }) {
  const s = server ?? localStats(entries);
  const scope = server ? "all visitors" : "this browser";
  return (
    <section className="hud" aria-label={`Prompt checks, ${scope}`}>
      <div className="cell hudbox">
        <div className="num">{s.blocked}</div>
        <div className="lbl">blocked</div>
      </div>
      <div className="cell hudbox">
        <div className="num s">{s.allowed}</div>
        <div className="lbl">allowed</div>
      </div>
      <div className="cell hudbox">
        <div className="num s">{ms(s.heuristics_avg_ms)}</div>
        <div className="lbl">heuristics avg</div>
      </div>
      <div className="cell hudbox">
        <div className="num">{ms(s.judge_avg_ms)}</div>
        <div className="lbl">judge avg</div>
      </div>
      <p className="hud-scope">prompt checks &middot; {scope}</p>
    </section>
  );
}
