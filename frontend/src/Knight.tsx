import { useId } from "react";
import { BASE, BLOOM, CORE, EYES, FLAME, GLOW, type Layer } from "./knightArt";

export type KnightState = "idle" | "safe" | "unsafe";

function Pixels({ layer }: { layer: Layer }) {
  return (
    <>
      {layer.map(([fill, d]) => (
        <path key={fill} d={d} fill={fill} />
      ))}
    </>
  );
}

const TITLES: Record<KnightState, string> = {
  idle: "Guardian knight, watching",
  safe: "Guardian knight, eyes glowing green: safe",
  unsafe: "Guardian knight, eye burning red: threat blocked",
};

// Little mint twinkles around the helmet when a prompt is safe: [x, y, delay in s].
const SPARKLES: [number, number, number][] = [
  [20, 12, 0],
  [51, 9, 0.7],
  [24, 5, 1.4],
  [49, 17, 2.1],
];

// Pixel-art portrait of the guardian. The eyes show the latest verdict:
// lilac and looking around while idle, smiling green with twinkles when safe,
// and a burning red eye with a flame trail when unsafe.
export default function Knight({ state }: { state: KnightState }) {
  const id = useId().replace(/:/g, "");
  return (
    <div className={`portrait portrait-${state}`}>
      {/* Square 50x50 view so the art scales by whole pixels at the CSS sizes used */}
      <svg
        viewBox="10 -1 50 50"
        width="100%"
        height="100%"
        shapeRendering="crispEdges"
        role="img"
        aria-label={TITLES[state]}
      >
        <defs>
          <filter id={`${id}-bloom`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.4" />
          </filter>
          <radialGradient id={`${id}-core`}>
            <stop offset="0%" stopColor="#ffd2b0" stopOpacity="0.9" />
            <stop offset="45%" stopColor="#ff5a46" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#ff3b5c" stopOpacity="0" />
          </radialGradient>
        </defs>
        <Pixels layer={BASE} />

        {/* key forces a remount so each new state fades in */}
        <g key={state} className="kn-state">
          {state !== "unsafe" && (
            <g className="kn-glow">
              <Pixels layer={GLOW[state]} />
            </g>
          )}
          <g className="kn-eyes">
            <g className="kn-lids">
              <Pixels layer={EYES[state]} />
            </g>
          </g>

          {state === "safe" &&
            SPARKLES.map(([x, y, delay]) => (
              <g key={`${x}-${y}`} className="kn-spark" style={{ animationDelay: `${delay}s` }}>
                <rect className="kn-sp-ray" x={x - 1} y={y} width="3" height="1" />
                <rect className="kn-sp-ray" x={x} y={y - 1} width="1" height="3" />
                <rect className="kn-sp-core" x={x} y={y} width="1" height="1" />
              </g>
            ))}

          {state === "unsafe" && (
            <g className="kn-fire">
              {FLAME.map((frame, i) => (
                <g key={i} className={`kn-frame kn-f${i}`}>
                  <Pixels layer={frame} />
                  <g className="kn-bloom" filter={`url(#${id}-bloom)`} shapeRendering="auto">
                    <Pixels layer={BLOOM[i]} />
                  </g>
                </g>
              ))}
              <ellipse className="kn-core" cx={CORE.x} cy={CORE.y} rx="6.5" ry="5" fill={`url(#${id}-core)`} />
            </g>
          )}
        </g>
      </svg>
    </div>
  );
}
