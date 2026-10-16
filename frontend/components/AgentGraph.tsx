"use client";
// The agent pipeline as a live graph: the agent that is working lights up. Shown in place of the loading line while the run is busy.
import { useEffect, useRef, useState } from "react";
import type { RunEvent } from "@/lib/types";

export type AgentId = "intake" | "planner" | "sketch" | "designer" | "style" | "render" | "reviewer" | "gate" | "executor" | "handoff";
export type AgentTrack = { active?: AgentId; prev?: AgentId; visited: AgentId[]; version?: number };

const NODES: { id: AgentId; label: string; role: string }[] = [
  { id: "intake", label: "Intake", role: "Reading the brief…" },
  { id: "planner", label: "Planner", role: "Planning the direction…" },
  { id: "sketch", label: "Sketchers", role: "Sketching every page…" },
  { id: "designer", label: "Designer", role: "Designing a page from its sketch…" },
  { id: "style", label: "Style lock", role: "Locking the style…" },
  { id: "render", label: "Render & audit", role: "Rendering and auditing…" },
  { id: "reviewer", label: "Reviewer", role: "Reviewing against the rubric…" },
  { id: "gate", label: "Gate", role: "Deciding whether to keep, revert or stop…" },
  { id: "executor", label: "Executor", role: "Fixing issues…" },
  { id: "handoff", label: "Handoff", role: "Building the handoff package…" },
];

const EDGES: [AgentId, AgentId][] = [
  ["intake", "planner"], ["planner", "sketch"], ["sketch", "designer"], ["designer", "style"], ["style", "render"],
  ["render", "reviewer"], ["reviewer", "gate"], ["gate", "executor"], ["executor", "render"], ["gate", "handoff"],
];

type Layout = { w: number; h: number; box: [number, number]; at: Record<AgentId, [number, number]>; loop: [number, number]; gateLabel: "below" | "right" };

/** Wide: one row into the refine loop. Narrow: a two-column snake that fits a phone. */
const WIDE: Layout = {
  w: 1040, h: 230, box: [104, 44], loop: [784, 115], gateLabel: "below",
  at: { intake: [60, 115], planner: [188, 115], sketch: [316, 115], designer: [444, 115], style: [572, 115],
        render: [708, 60], reviewer: [860, 60], gate: [860, 170], executor: [708, 170], handoff: [982, 170] },
};
const NARROW: Layout = {
  w: 340, h: 440, box: [128, 44], loop: [170, 295], gateLabel: "right",
  at: { intake: [80, 30], planner: [260, 30], sketch: [260, 100], designer: [80, 100], style: [80, 170],
        render: [80, 250], reviewer: [260, 250], gate: [260, 340], executor: [80, 340], handoff: [260, 412] },
};
const GATE = 24; // half-diagonal of the gate diamond

/** Which agent an event means is now working. */
const ON: Record<string, AgentId> = {
  intake: "planner", kickoff_answered: "intake", kickoff_skipped: "planner", revising: "planner",
  direction: "sketch", sketch_started: "sketch", sketches_approved: "designer", design_started: "designer", design_ready: "style",
  style_locked: "render", render_started: "render", review_started: "reviewer", gate: "gate", execute_started: "executor",
  execute_done: "render", changes_requested: "executor", approved: "handoff",
};
const NODE_EVENT: Record<string, AgentId> = { intake: "intake", plan_direction: "planner" };

export const initialTrack: AgentTrack = { visited: [] };

export function trackAgent(t: AgentTrack, e: RunEvent): AgentTrack {
  const id = e.type === "node" ? NODE_EVENT[e.node] : ON[e.type];
  const version: number | undefined = e.version ?? t.version;
  if (!id || id === t.active) return version === t.version ? t : { ...t, version };
  return { active: id, prev: t.active, visited: t.visited.includes(id) ? t.visited : [...t.visited, id], version };
}

function half(id: AgentId, L: Layout): [number, number] {
  return id === "gate" ? [GATE, GATE] : [L.box[0] / 2, L.box[1] / 2];
}

function edgePath(a: AgentId, b: AgentId, L: Layout): string {
  const [ax, ay] = L.at[a], [bx, by] = L.at[b];
  const [ahw, ahh] = half(a, L), [bhw, bhh] = half(b, L);
  if (ay === by) { const d = Math.sign(bx - ax); return `M${ax + d * ahw},${ay} H${bx - d * (bhw + 3)}`; }
  if (ax === bx) { const d = Math.sign(by - ay); return `M${ax},${ay + d * ahh} V${by - d * (bhh + 3)}`; }
  // Elbow: leave sideways, turn halfway, arrive sideways.
  const d = Math.sign(bx - ax), x0 = ax + d * ahw, x1 = bx - d * (bhw + 3), mid = (x0 + x1) / 2;
  return `M${x0},${ay} H${mid} V${by} H${x1}`;
}

export function AgentGraph({ track, caption }: { track: AgentTrack; caption: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setNarrow(e.contentRect.width < 600));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const L = narrow ? NARROW : WIDE;
  const active = NODES.find((n) => n.id === track.active);
  const [bw, bh] = L.box;

  return (
    <div ref={ref} className="agent-graph">
      <svg viewBox={`0 0 ${L.w} ${L.h}`} className={`agent-graph__svg ${narrow ? "is-narrow" : ""}`} role="img"
        aria-label={`Agent pipeline${active ? `: ${active.label} is working` : ""}`}>
        <defs>
          <marker id="ag-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 z" className="ag-arrow" />
          </marker>
          <marker id="ag-arrow-on" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 z" className="ag-arrow ag-arrow--on" />
          </marker>
        </defs>

        <text x={L.loop[0]} y={L.loop[1]} className={`ag-loop ${track.version ? "is-on" : ""}`} textAnchor="middle" dominantBaseline="middle">
          {track.version ? `↻ v${track.version}` : "refine loop"}
        </text>

        {EDGES.map(([a, b]) => {
          const on = track.prev === a && track.active === b;
          return <path key={`${a}-${b}`} d={edgePath(a, b, L)} className={`ag-edge ${on ? "is-on" : ""}`}
            markerEnd={`url(#${on ? "ag-arrow-on" : "ag-arrow"})`} />;
        })}

        {NODES.map((n) => {
          const [x, y] = L.at[n.id];
          const state = n.id === track.active ? "is-active" : track.visited.includes(n.id) ? "is-done" : "";
          return (
            <g key={n.id} className={`ag-node ${state}`}>
              {n.id === "gate"
                ? <path d={`M${x},${y - GATE} L${x + GATE},${y} L${x},${y + GATE} L${x - GATE},${y} z`} className="ag-shape" />
                : <rect x={x - bw / 2} y={y - bh / 2} width={bw} height={bh} rx={10} className="ag-shape" />}
              {n.id === "gate" && L.gateLabel === "right"
                ? <text x={x + GATE + 8} y={y} dominantBaseline="middle" className="ag-label">{n.label}</text>
                : <text x={x} y={n.id === "gate" ? y + GATE + 14 : y} textAnchor="middle" dominantBaseline="middle" className="ag-label">{n.label}</text>}
            </g>
          );
        })}
      </svg>
      <p className="agent-graph__caption" role="status"><span className="spinner" />{caption || active?.role || "Starting…"}</p>
    </div>
  );
}
