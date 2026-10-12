"use client";
import { useEffect, useRef, useState } from "react";
import { artifactUrl } from "@/lib/api";
import { CRITERIA } from "@/lib/logic";
import type { CheckSummary, Issue, Score } from "@/lib/types";

/** Generated HTML always renders in a sandboxed iframe with no same-origin access (§3.3). */
export function ScaledFrame({ runId, path, width = 1440, height = 900, title }: {
  runId: string; path: string; width?: number; height?: number; title: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.3);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setScale(e.contentRect.width / width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [width]);
  return (
    <div ref={ref} className="frame" style={{ height: height * scale }}>
      <iframe title={title} sandbox="allow-scripts" src={artifactUrl(runId, path)} loading="lazy"
        style={{ width, height, transform: `scale(${scale})` }} />
    </div>
  );
}

export function Shot({ runId, path, alt, tall }: { runId: string; path?: string; alt: string; tall?: boolean }) {
  if (!path) return <div className={`shot shot--empty ${tall ? "shot--tall" : ""}`}>No screenshot</div>;
  // eslint-disable-next-line @next/next/no-img-element
  return <img className={`shot ${tall ? "shot--tall" : ""}`} src={artifactUrl(runId, path)} alt={alt} loading="lazy" />;
}

export function AuditBadges({ checks }: { checks: CheckSummary[] }) {
  const failing = checks.filter((c) => !c.passed);
  if (!checks.length) return null;
  return (
    <div className="audit-badges">
      {failing.length === 0
        ? <span className="badge badge--ok">✓ All {checks.length} automatic checks pass</span>
        : failing.map((c) => c.blocking === false
          ? <span key={c.id} className="badge badge--warn" title={c.details}>! {c.name}</span>
          : <span key={c.id} className="badge badge--bad" title={c.details}>✗ {c.name}</span>)}
    </div>
  );
}

/** Score trajectory: one series, threshold rule, hover tooltip per point. */
export function ScoreChart({ points, threshold = 4 }: { points: { version: number; score: number | null }[]; threshold?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const data = points.filter((p) => p.score != null) as { version: number; score: number }[];
  if (!data.length) return null;
  const W = 320, H = 150, L = 28, R = 12, T = 12, B = 26;
  const x = (i: number) => L + (data.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (data.length - 1));
  const y = (s: number) => T + ((5 - s) / 4) * (H - T - B);
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d.score)}`).join(" ");
  return (
    <figure className="chart">
      <figcaption className="chart__title">Overall score by version</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Score by version: ${data.map((d) => `v${d.version} ${d.score}`).join(", ")}`}>
        {[1, 2, 3, 4, 5].map((s) => (
          <g key={s}>
            <line className="chart__grid" x1={L} x2={W - R} y1={y(s)} y2={y(s)} />
            <text className="chart__tick" x={L - 8} y={y(s) + 4} textAnchor="end">{s}</text>
          </g>
        ))}
        <line className="chart__threshold" x1={L} x2={W - R} y1={y(threshold)} y2={y(threshold)} />
        <text className="chart__tick chart__tick--label" x={L + 4} y={y(threshold) + 13} textAnchor="start">pass {threshold.toFixed(1)}</text>
        <path className="chart__line" d={path} />
        {data.map((d, i) => (
          <g key={d.version} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}>
            <circle className="chart__hit" cx={x(i)} cy={y(d.score)} r={14} />
            <circle className="chart__dot" cx={x(i)} cy={y(d.score)} r={hover === i ? 6 : 4.5} />
            <text className="chart__tick" x={x(i)} y={H - 8} textAnchor="middle">v{d.version}</text>
          </g>
        ))}
        {hover != null && (
          <g className="chart__tip" transform={`translate(${Math.min(Math.max(x(hover), L + 36), W - R - 36)},${Math.max(y(data[hover].score) - 30, 2)})`}>
            <rect x={-36} y={0} width={72} height={22} rx={4} />
            <text x={0} y={15} textAnchor="middle">v{data[hover].version}: {data[hover].score.toFixed(2)}</text>
          </g>
        )}
      </svg>
      <table className="sr-only"><tbody>{data.map((d) => <tr key={d.version}><td>v{d.version}</td><td>{d.score}</td></tr>)}</tbody></table>
    </figure>
  );
}

/** Per-criterion scores as thin horizontal bars (magnitude, one hue). */
export function ScoreBars({ scores, previous }: { scores: Score[]; previous?: Score[] }) {
  return (
    <ul className="bars">
      {scores.map((s) => {
        const prev = previous?.find((p) => p.criterion === s.criterion)?.score;
        const delta = prev != null ? s.score - prev : 0;
        return (
          <li key={s.criterion} title={s.evidence}>
            <span className="bars__label">{CRITERIA[s.criterion] ?? s.criterion}</span>
            <span className="bars__track"><span className="bars__fill" style={{ width: `${(s.score / 5) * 100}%` }} /></span>
            <span className="bars__value">{s.score}/5{delta !== 0 && <em className={delta > 0 ? "up" : "down"}>{delta > 0 ? ` ▲${delta}` : ` ▼${-delta}`}</em>}</span>
          </li>
        );
      })}
    </ul>
  );
}

const SEV_LABEL = { high: "Must fix", medium: "Should fix", low: "Polish" } as const;

export function IssueItem({ issue, fixed }: { issue: Issue; fixed?: boolean }) {
  return (
    <li className={`issue ${fixed ? "issue--fixed" : ""}`}>
      <div className="issue__head">
        <span className={`sev sev--${issue.severity}`}>{fixed ? "✓ Fixed" : issue.status === "regressed" ? "↺ Came back" : SEV_LABEL[issue.severity]}</span>
        <span className="issue__crit">{CRITERIA[issue.criterion] ?? issue.criterion} · {issue.viewport}</span>
      </div>
      <p className="issue__why"><strong>Why it matters:</strong> {issue.explanation}</p>
      <details>
        <summary>Details</summary>
        <p><strong>Found:</strong> {issue.evidence}</p>
        <p><strong>Fix:</strong> {issue.suggested_fix}</p>
        <p className="mono">{issue.selector}</p>
      </details>
    </li>
  );
}
