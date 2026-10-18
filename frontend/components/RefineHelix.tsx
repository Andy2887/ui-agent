"use client";
// Design stage: the refine loop in 3D. Each lap (render → review → gate → fix) is a ring; when the fixer finishes, the dot
// climbs to a new ring, so the stack shows every version and its score. Narrow screens and reduced motion get the flat AgentGraph.
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AgentGraph, NODES, type AgentId, type AgentTrack } from "./AgentGraph";

export type Lap = { version: number; score: number | null; decision?: string };

const R = 120, GAP = 46, CAP = 4, W = 680, H = 430, C = 2 * Math.PI * R;
const POS: Partial<Record<AgentId, [number, number]>> = {
  render: [-R, 0], reviewer: [0, -R], gate: [R, 0], executor: [0, R], designer: [-R - 150, 140], style: [-R - 70, 80],
};
const ANG: Partial<Record<AgentId, number>> = { render: 180, reviewer: 270, gate: 360, executor: 450 }; // one lap runs 180 → 540
const RING_NODES: AgentId[] = ["render", "reviewer", "gate", "executor"];
const TAG: Record<string, string> = { revert: "reverted", pass: "pass", plateau: "plateau", max_iters: "round limit", budget: "budget" };
const label = (id: AgentId) => NODES.find((n) => n.id === id)!.label;
const ease = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const at = (x: number, y: number) => ({ "--x": `${x}px`, "--y": `${y}px` }) as CSSProperties;

type Tween = { t0: number; dur: number; fn: (k: number) => void; done?: () => void };

export function RefineHelix({ track, caption, laps }: { track: AgentTrack; caption: string; laps: Lap[] }) {
  const outer = useRef<HTMLDivElement>(null), stage = useRef<HTMLDivElement>(null), helix = useRef<HTMLDivElement>(null);
  const stations = useRef<HTMLDivElement>(null), dot = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(W);
  const [reduced, setReduced] = useState(false);
  const view = useRef({ tilt: 58, yaw: -18 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  // Animated state lives in a ref and is written straight to the DOM each frame, so React never re-renders 60 times a second.
  const m = useRef({ lift: 0, x: 0, y: 0, z: 0, theta: null as number | null, level: 0, place: undefined as AgentId | undefined, tween: null as Tween | null });

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    if (outer.current) ro.observe(outer.current);
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const onMq = () => setReduced(mq.matches);
    onMq(); mq.addEventListener("change", onMq);
    return () => { ro.disconnect(); mq.removeEventListener("change", onMq); };
  }, []);
  const flat = width < 600 || reduced;

  // One ring per version that has been reviewed, plus the one under review now. The fixer's new version gets its ring when it renders.
  const active = track.active;
  const reviewing = active === "render" || active === "reviewer" || active === "gate";
  const versions = [...new Set([...laps.map((l) => l.version), ...(reviewing && track.version ? [track.version] : [])])].sort((a, b) => a - b);
  const rings = versions.length ? versions : [0]; // 0: a blank ring before v1 renders
  const top = rings.length - 1;
  const hidden = top - CAP + 1;

  // Move the dot whenever the active agent or the top ring changes. A new event retargets from wherever the dot is now.
  useEffect(() => {
    const s = m.current, to = active;
    if (flat || !to || !POS[to] || (to === s.place && top === s.level)) return;
    const [x1, y1] = POS[to]!, z1 = to in ANG ? top * GAP : 0, a = ANG[to];
    if (s.place === undefined) {
      Object.assign(s, { x: x1, y: y1, z: z1, lift: top * GAP, theta: a ?? null, level: top, place: to, tween: null });
      return;
    }
    const lift0 = s.lift, z0 = s.z, lift1 = top * GAP;
    if (a !== undefined && s.theta !== null) {
      const a0 = s.theta, a1 = a0 + (((a - a0) % 360) + 360) % 360; // always forward around the ring
      const climb = top > s.level; // lap done: rise to the next ring while finishing the circle
      s.tween = { t0: performance.now(), dur: climb ? 1200 : 950,
        fn: (k) => { s.theta = a0 + (a1 - a0) * k; s.z = z0 + (z1 - z0) * k; s.lift = lift0 + (lift1 - lift0) * k; },
        done: () => { if (s.theta! > 540) s.theta! -= 360; s.level = top; } };
    } else {
      const x0 = s.x, y0 = s.y;
      s.theta = null;
      s.tween = { t0: performance.now(), dur: 800,
        fn: (k) => { s.x = x0 + (x1 - x0) * k; s.y = y0 + (y1 - y0) * k; s.z = z0 + (z1 - z0) * k; s.lift = lift0 + (lift1 - lift0) * k; },
        done: () => { s.theta = a ?? null; s.level = top; } };
    }
    s.place = to;
  }, [active, top, flat]);

  // One loop writes every transform, so the dot, the rings and the labels never drift apart.
  useEffect(() => {
    if (flat) { m.current.place = undefined; return; } // remount from scratch after a fallback
    let raf = 0;
    const frame = (now: number) => {
      const s = m.current, v = view.current, tw = s.tween;
      if (tw) {
        const k = Math.min(1, (now - tw.t0) / tw.dur);
        tw.fn(ease(k));
        if (k === 1) { s.tween = null; tw.done?.(); }
      }
      if (s.theta !== null) {
        const r = (s.theta * Math.PI) / 180;
        s.x = Math.cos(r) * R; s.y = Math.sin(r) * R;
        const prog = stage.current?.querySelector<SVGCircleElement>(`[data-ring="${s.level}"] .rh-progress`);
        if (prog) prog.style.strokeDashoffset = String(C * (1 - clamp((s.theta - 180) / 360, 0, 1)));
      }
      stage.current?.style.setProperty("--tilt", `${v.tilt}deg`);
      stage.current?.style.setProperty("--yaw", `${v.yaw}deg`);
      if (helix.current) helix.current.style.transform = `rotateX(${v.tilt}deg) rotateZ(${v.yaw}deg) translateZ(${-s.lift}px)`;
      if (stations.current) stations.current.style.transform = `translateZ(${s.lift}px)`;
      if (dot.current) dot.current.style.transform = `translate3d(${s.x}px, ${s.y}px, ${s.z}px) rotateZ(${-v.yaw}deg) rotateX(${-v.tilt}deg) translate(-50%, -50%)`;
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [flat]);

  // One wrapper in both modes, so the ResizeObserver keeps watching the same element across a fallback.
  if (flat) return <div ref={outer}><AgentGraph track={track} caption={caption} /></div>;

  const node = (id: AgentId) => `rh-node ${id === active ? "is-active" : track.visited.includes(id) ? "is-done" : ""}`;
  const lapOf = new Map(laps.map((l) => [l.version, l]));
  const scale = Math.min(1, width / W);
  const role = NODES.find((n) => n.id === active)?.role;

  return (
    <div ref={outer}><div className="agent-graph rh">
      <div className="rh__top">
        <span className="rh-chip"><span className="rh-tick">✓</span>Intake · Planner · Sketchers</span>
        <span className="rh__top-right">
          {hidden > 0 && <span className="rh-chip">{hidden === 1 ? `v${rings[0]}` : `v${rings[0]}–v${rings[hidden - 1]}`} below</span>}
          {track.version && <span className="rh-chip rh-chip--on">↻ v{track.version}</span>}
        </span>
      </div>
      <div className="rh__fit" style={{ height: H * scale }}>
        <div ref={stage} className="rh__stage" style={{ transform: `translateX(-50%) scale(${scale})` }} tabIndex={0} role="img" title="Drag to turn"
          aria-label={`Agent pipeline${active ? `: ${label(active)} is working` : ""}${track.version ? `, version ${track.version}` : ""}`}
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId); }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            const v = view.current;
            v.yaw += (e.clientX - drag.current.x) * 0.35; v.tilt = clamp(v.tilt - (e.clientY - drag.current.y) * 0.25, 0, 75);
            drag.current = { x: e.clientX, y: e.clientY };
          }}
          onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
          onKeyDown={(e) => {
            const d = ({ ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, 5], ArrowDown: [0, -5] } as Record<string, number[]>)[e.key];
            if (!d) return;
            e.preventDefault(); view.current.yaw += d[0]; view.current.tilt = clamp(view.current.tilt + d[1], 0, 75);
          }}>
          <div ref={helix} className="rh__helix">
            {rings.map((v, i) => {
              const age = top - i, lap = lapOf.get(v);
              const prevBest = Math.max(-Infinity, ...laps.filter((l) => l.version < v && l.score != null).map((l) => l.score!));
              const delta = lap?.score != null && prevBest > -Infinity ? lap.score - prevBest : null;
              const tag = lap?.decision && TAG[lap.decision];
              return (
                <div key={v} data-ring={i} className={`rh-ring ${age === 0 ? "is-current" : "is-past"}`}
                  style={{ transform: `translateZ(${i * GAP}px)`, "--fade": age === 0 ? 1 : age < CAP ? 0.72 - 0.16 * age : 0 } as CSSProperties}>
                  <svg className="rh-plane" viewBox="-340 -340 680 680" aria-hidden="true">
                    <circle className="rh-track" r={R} />
                    <circle className="rh-progress" r={R} transform="rotate(180)" strokeDasharray={C} strokeDashoffset={C} />
                    {RING_NODES.map((id) => id === "gate"
                      ? <path key={id} className="rh-mark" d={`M${R},-7 L${R + 7},0 L${R},7 L${R - 7},0 z`} />
                      : <circle key={id} className="rh-mark" cx={POS[id]![0]} cy={POS[id]![1]} r={4} />)}
                    {i === 0 && <>
                      <path className="rh-path" d={`M${POS.designer} L${POS.style} L${POS.render}`} />
                      <circle className="rh-mark" cx={POS.designer![0]} cy={POS.designer![1]} r={4} />
                      <circle className="rh-mark" cx={POS.style![0]} cy={POS.style![1]} r={4} />
                    </>}
                  </svg>
                  {i === 0 && (["designer", "style"] as AgentId[]).map((id) =>
                    <div key={id} className="rh-bb" style={at(...POS[id]!)}><span className={node(id)}>{label(id)}</span></div>)}
                  {v > 0 && (
                    <div className="rh-bb rh-bb--right" style={at(Math.cos(Math.PI / 6) * (R + 14), Math.sin(Math.PI / 6) * (R + 14))}>
                      <span className="rh-ver">
                        <b>v{v}</b> {lap?.score != null ? lap.score.toFixed(2) : "…"}
                        {tag ? <span className={`tag tag--${lap!.decision}`}>{tag}</span>
                          : delta != null && <span className={`tag ${delta >= 0 ? "tag--continue" : ""}`}>{delta >= 0 ? "+" : "−"}{Math.abs(delta).toFixed(2)}</span>}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={stations} className="rh__stations">
              {RING_NODES.map((id) => (
                <div key={id} className={`rh-bb ${id === "executor" ? "rh-bb--down" : ""}`} style={at(...POS[id]!)}><span className={node(id)}>{label(id)}</span></div>
              ))}
            </div>
            <div ref={dot} className="rh-dot" />
          </div>
        </div>
      </div>
      <p className="agent-graph__caption" role="status"><span className="spinner" />{caption || role || "Starting…"}</p>
    </div></div>
  );
}
