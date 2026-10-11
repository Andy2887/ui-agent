"use client";
// Screens 2–7: Kickoff, Sketching, Pick a sketch, Designing & refining, Final review, Download — all driven by the run's SSE events.
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, artifactUrl, downloadUrl, eventsUrl } from "@/lib/api";
import { SLOT_LABEL, STOP_REASON } from "@/lib/logic";
import type { Brief, Design, DesignBrief, GalleryCandidate, Issue, KickoffQuestion, RunEvent, Snapshot } from "@/lib/types";
import { AuditBadges, IssueItem, ScaledFrame, ScoreBars, ScoreChart, Shot } from "./RunParts";

type RunState = {
  status: string; error?: string; mock?: boolean; request?: any; productName?: string;
  intake?: DesignBrief;
  kickoff?: { intake: DesignBrief; questions: KickoffQuestion[] };
  briefs: Brief[]; repairs: string[];
  candidates: Record<string, { brief?: Brief; design?: Design; started: boolean }>;
  gallery?: { design_brief: DesignBrief; candidates: GalleryCandidate[]; candidate_count: number };
  final?: any;
  picked?: { id: string; notes: string };
  iterations: { iteration: number; snapshot: Snapshot }[];
  gates: Record<number, { decision: string; note?: string }>;
  activity: string;
  done?: any;
};

const initial: RunState = { status: "connecting", briefs: [], repairs: [], candidates: {}, iterations: [], gates: {}, activity: "" };

function reduce(s: RunState, e: RunEvent): RunState {
  switch (e.type) {
    case "status":
      return { ...s, status: e.status, error: e.error ?? (e.status === "error" ? s.error : undefined), mock: e.mock ?? s.mock, request: e.request ?? s.request,
               done: e.status === "done" ? e : s.done };
    case "intake": return { ...s, intake: e.intake, productName: e.intake?.product_name, activity: "Planning directions…" };
    case "kickoff_answered": return { ...s, activity: "Updating the brief with your answers…" };
    case "kickoff_skipped": return { ...s, activity: "Planning directions…" };
    case "plan_retry": return { ...s, activity: `Directions were too similar; re-planning (attempt ${e.attempt + 1})…` };
    case "briefs": {
      const candidates: RunState["candidates"] = {};
      for (const b of e.briefs as Brief[]) candidates[b.id] = { brief: b, started: false };
      return { ...s, briefs: e.briefs, repairs: e.repairs ?? [], candidates, gallery: undefined, activity: "Sketching directions…" };
    }
    case "candidate_started": return { ...s, candidates: { ...s.candidates, [e.id]: { ...s.candidates[e.id], started: true } } };
    case "candidate_ready": return { ...s, candidates: { ...s.candidates, [e.id]: { brief: e.brief, design: e.design, started: true } } };
    case "interrupt":
      if (e.kind === "kickoff") return { ...s, kickoff: e.payload, activity: "" };
      return e.kind === "gallery" ? { ...s, gallery: e.payload, activity: "" } : { ...s, final: e.payload, activity: "" };
    case "picked": return { ...s, picked: { id: e.id, notes: e.notes }, activity: `Designing ${e.id.toUpperCase()} in full from the sketch…` };
    case "design_ready": return { ...s, activity: "Locking the style…" };
    case "regenerating": return { ...s, picked: undefined, iterations: [], activity: "Re-planning with your feedback…" };
    case "style_locked": return { ...s, activity: "Starting refinement…" };
    case "render_started": return { ...s, activity: `Rendering v${e.version} at 375, 768 and 1440px…` };
    case "review_started": return { ...s, activity: `Reviewing v${e.version} against the rubric…` };
    case "execute_started": return { ...s, activity: `Fixing ${e.issues.length} issue${e.issues.length === 1 ? "" : "s"} → v${e.version}…` };
    case "iteration": return { ...s, iterations: [...s.iterations.filter((i) => i.snapshot.version !== e.snapshot.version), { iteration: e.iteration, snapshot: e.snapshot }] };
    case "gate": return { ...s, gates: { ...s.gates, [e.iteration]: { decision: e.decision, note: e.note } } };
    case "changes_requested": return { ...s, final: undefined, activity: "Applying your changes…" };
    case "approved": return { ...s, activity: "Building the handoff package…" };
    case "handoff_built": return { ...s, activity: "Exporting…" };
    default: return s;
  }
}

function Steps({ phase }: { phase: number }) {
  const steps = ["Kickoff", "Sketches", "Design", "Review", "Download"];
  return (
    <ol className="steps">
      {steps.map((st, i) => <li key={st} className={i < phase ? "is-done" : i === phase ? "is-current" : ""} aria-current={i === phase ? "step" : undefined}>{st}</li>)}
    </ol>
  );
}

export function RunView({ runId }: { runId: string }) {
  const [state, setState] = useState<RunState>(initial);
  const [lost, setLost] = useState(false);

  useEffect(() => {
    let seq = 0;
    let es: EventSource | null = null;
    let s: RunState = initial;
    const connect = () => {
      es = new EventSource(eventsUrl(runId, seq));
      es.onmessage = (m) => {
        const e: RunEvent = JSON.parse(m.data);
        if (e.seq < seq) return; // the browser's auto-reconnect replays from the start
        seq = e.seq + 1;
        s = reduce(s, e);
        setState(s);
        setLost(false);
      };
      es.onerror = () => { setLost(true); };
    };
    connect();
    return () => es?.close();
  }, [runId]);

  const phase = state.status === "done" ? 4 : state.final ? 3 : state.picked ? 2 : state.briefs.length || state.gallery ? 1 : 0;
  const brief = state.request?.brief;

  return (
    <div className="page">
      <header className="page-head page-head--row">
        <div>
          <h1>{brief?.product_name || state.productName || "Design run"}</h1>
          <p className="muted clamp">{brief?.problem ?? state.request?.prompt}</p>
        </div>
        <Steps phase={phase} />
      </header>
      {state.mock && <p className="callout">Mock mode: sketches, designs, reviews and fixes come from offline stand-ins, not Claude.</p>}
      {lost && state.status !== "done" && <p className="callout callout--warn">Connection lost. Reconnecting…</p>}
      {state.status === "error" && <div className="callout callout--error"><strong>The run stopped with an error.</strong><pre>{state.error}</pre></div>}
      {state.activity && state.status === "running" && <p className="activity" role="status"><span className="spinner" aria-hidden="true" />{state.activity}</p>}

      {phase === 0 && state.status === "waiting_kickoff" && state.kickoff && <Kickoff runId={runId} kickoff={state.kickoff} />}
      {phase === 0 && state.status !== "waiting_kickoff" && <div className="empty"><span className="spinner" /> The designer is reading your brief…</div>}
      {phase === 1 && state.status === "waiting_gallery" && state.gallery && <Gallery runId={runId} gallery={state.gallery} />}
      {phase === 1 && state.status !== "waiting_gallery" && <Sketching state={state} runId={runId} />}
      {phase === 2 && <Refining state={state} runId={runId} />}
      {phase === 3 && state.final && <FinalReview runId={runId} state={state} />}
      {phase === 4 && <Download runId={runId} state={state} />}
    </div>
  );
}

/* --------------------------------------------------------------- Design brief */

function DesignBriefCard({ brief, open }: { brief: DesignBrief; open?: boolean }) {
  return (
    <details className="design-brief aside-card" open={open}>
      <summary>The design brief <span className="muted">how the designer read your request</span></summary>
      <dl>
        <dt>Problem</dt><dd>{brief.problem}</dd>
        <dt>Users</dt><dd>{brief.audience}</dd>
        <dt>They need to</dt><dd><ul>{brief.user_needs.map((n) => <li key={n}>{n}</li>)}</ul></dd>
        <dt>Primary action</dt><dd>{brief.primary_action}</dd>
        {brief.assumptions.length > 0 && <><dt>Assumptions</dt><dd><ul>{brief.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></dd></>}
      </dl>
    </details>
  );
}

/* --------------------------------------------------------------------- Kickoff */

function Kickoff({ runId, kickoff }: { runId: string; kickoff: NonNullable<RunState["kickoff"]> }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async (given: Record<string, string>) => {
    setBusy(true); setErr(null);
    try { await api.resume(runId, { action: "answer", answers: given }); } catch (e) { setErr((e as Error).message); setBusy(false); }
  };
  const answered = Object.values(answers).some((a) => a.trim());
  return (
    <section className="kickoff">
      <div className="kickoff__questions">
        <div className="section-bar">
          <h2 className="h2">Before sketching, a few questions</h2>
          <p className="muted">Your answers change what gets sketched. Skip anything you&apos;re unsure about; the designer will assume.</p>
        </div>
        {kickoff.questions.map((q) => (
          <div key={q.id} className="aside-card question">
            <label className="field"><span>{q.question}</span>
              <input value={answers[q.id] ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))} placeholder="Your answer" /></label>
            <div className="chips" role="group" aria-label="Suggested answers">
              {q.suggestions.map((sug) => (
                <button key={sug} className={`chip ${answers[q.id] === sug ? "is-on" : ""}`} aria-pressed={answers[q.id] === sug}
                  onClick={() => setAnswers((a) => ({ ...a, [q.id]: sug }))}>{sug}</button>
              ))}
            </div>
            <p className="note">Why it matters: {q.why}</p>
          </div>
        ))}
        <div className="kickoff__actions">
          <button className="btn btn--primary" disabled={busy || !answered} onClick={() => send(answers)}>Continue to sketches →</button>
          <button className="link" disabled={busy} onClick={() => send({})}>Skip, use your best judgement</button>
        </div>
        {err && <p className="callout callout--error">{err}</p>}
      </div>
      <DesignBriefCard brief={kickoff.intake} open />
    </section>
  );
}

/* ---------------------------------------------------------------------- Mood */

/** Load a Google Font for the mood swatch; one link per family so one unknown name can't break the rest. */
function useGoogleFonts(families: string[]) {
  const key = families.join("|");
  useEffect(() => {
    for (const f of key.split("|")) {
      const id = `gf-${f.replace(/\W+/g, "-")}`;
      if (!f || document.getElementById(id)) continue;
      const link = document.createElement("link");
      link.id = id; link.rel = "stylesheet";
      link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(f).replace(/%20/g, "+")}&display=swap`;
      document.head.appendChild(link);
    }
  }, [key]);
}

function Mood({ brief }: { brief: Brief }) {
  useGoogleFonts([brief.heading_font, brief.body_font]);
  const p = brief.palette;
  const heading = `"${brief.heading_font}", system-ui, sans-serif`;
  const body = `"${brief.body_font}", system-ui, sans-serif`;
  return (
    <div className="mood" style={{ background: p.bg, color: p.text, borderColor: p.border }} aria-label={`Proposed mood: ${brief.mood.join(", ")}`}>
      <span className="mood__aa" style={{ fontFamily: heading }} aria-hidden="true">Aa</span>
      <div className="mood__meta">
        <span className="mood__words" style={{ fontFamily: heading }}>{brief.mood.join(" · ")}</span>
        <span className="mood__fonts" style={{ fontFamily: body, color: p.muted }}>{brief.heading_font} / {brief.body_font} · {brief.theme}</span>
      </div>
      <div className="mood__swatches">
        {(["surface", "primary", "accent", "muted", "text"] as const).map((k) => <span key={k} title={`${k} ${p[k]}`} style={{ background: p[k], borderColor: p.border }} />)}
      </div>
      <span className="mood__btn" style={{ background: p.primary, color: p.on_primary, fontFamily: body }}>Button</span>
    </div>
  );
}

function DirectionText({ brief }: { brief: Brief }) {
  return (
    <>
      <div className="cand__head"><span className="letter">{brief.id.toUpperCase()}</span><h3>{brief.name}</h3><span className="tag">{SLOT_LABEL[brief.slot] ?? brief.slot}</span></div>
      <p className="cand__concept">{brief.concept}</p>
      <p className="cand__tradeoff"><strong>Trade-off:</strong> {brief.tradeoff}</p>
      <Mood brief={brief} />
    </>
  );
}

/* ------------------------------------------------------------------- Sketching */

function Sketching({ state, runId }: { state: RunState; runId: string }) {
  if (!state.briefs.length) return <div className="empty"><span className="spinner" /> Planning distinct directions…</div>;
  return (
    <section>
      <h2 className="h2">{state.briefs.length} direction{state.briefs.length > 1 ? "s" : ""}</h2>
      {state.repairs.length > 0 && <p className="note">Contrast adjusted in the proposed palettes: {state.repairs.join("; ")}</p>}
      <div className="grid grid--cards">
        {state.briefs.map((b) => {
          const c = state.candidates[b.id];
          return (
            <article key={b.id} className="cand">
              <div className="cand__media">
                {c?.design?.screenshots?.desktop ? <Shot runId={runId} path={c.design.screenshots.desktop} alt={`${b.name} sketch`} />
                  : c?.design?.error ? <div className="shot shot--empty">Sketch failed: {c.design.error}</div>
                  : <div className="shot shot--loading"><span className="spinner" />{c?.started ? "Sketching…" : "Queued"}</div>}
              </div>
              <div className="cand__body"><DirectionText brief={b} /></div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------- Gallery */

function Gallery({ runId, gallery }: { runId: string; gallery: NonNullable<RunState["gallery"]> }) {
  const [open, setOpen] = useState<string | null>(null);
  const [compare, setCompare] = useState<string[]>([]);
  const [pick, setPick] = useState<string | null>(gallery.candidates.length === 1 ? gallery.candidates[0].id : null);
  const [notes, setNotes] = useState("");
  const [regen, setRegen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [count, setCount] = useState(gallery.candidate_count);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const byId = Object.fromEntries(gallery.candidates.map((c) => [c.id, c]));

  const send = async (body: Record<string, unknown>) => {
    setBusy(true); setErr(null);
    try { await api.resume(runId, body); } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  const viewer = (c: GalleryCandidate) => (
    <div className="viewer">
      <div className="viewer__desktop"><span className="viewer__label">Desktop · 1440px</span><ScaledFrame runId={runId} path={c.html_path} title={`${c.name} desktop sketch`} /></div>
      <div className="viewer__mobile"><span className="viewer__label">Mobile · 375px</span><ScaledFrame runId={runId} path={c.html_path} width={375} height={760} title={`${c.name} mobile sketch`} /></div>
    </div>
  );

  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Pick a direction</h2>
        <p className="muted">Each sketch is a different bet on solving the problem. Judge the idea and the structure; the mood shows the look the designer proposes. Tick two to compare.</p>
      </div>
      <DesignBriefCard brief={gallery.design_brief} />
      {open && byId[open] && (
        <div className="viewer-panel">
          <div className="section-bar"><h3>{open.toUpperCase()} · {byId[open].name}</h3><button className="btn" onClick={() => setOpen(null)}>Close preview</button></div>
          {viewer(byId[open])}
        </div>
      )}
      {compare.length === 2 && (
        <div className="compare">
          {compare.map((id) => <div key={id}><h3>{id.toUpperCase()} · {byId[id].name}</h3><ScaledFrame runId={runId} path={byId[id].html_path} title={byId[id].name} /></div>)}
          <button className="btn" onClick={() => setCompare([])}>Close comparison</button>
        </div>
      )}
      <div className="grid grid--cards">
        {gallery.candidates.map((c) => (
          <article key={c.id} className={`cand ${pick === c.id ? "is-picked" : ""}`}>
            <button className="cand__media cand__media--btn" onClick={() => { setOpen(c.id); window.scrollTo({ top: 0, behavior: "smooth" }); }} aria-label={`Open ${c.name} sketch on desktop and mobile`}>
              {c.error ? <div className="shot shot--empty">Failed: {c.error}</div> : <Shot runId={runId} path={c.screenshots.desktop} alt={`${c.name} sketch`} />}
            </button>
            <div className="cand__body">
              <DirectionText brief={c.brief} />
              <div className="cand__actions">
                <button className={`btn ${pick === c.id ? "btn--primary" : ""}`} disabled={!!c.error} onClick={() => setPick(c.id)}>{pick === c.id ? "Selected" : "Choose this"}</button>
                <label className="check"><input type="checkbox" checked={compare.includes(c.id)} disabled={!compare.includes(c.id) && compare.length >= 2}
                  onChange={() => setCompare((x) => x.includes(c.id) ? x.filter((y) => y !== c.id) : [...x, c.id])} />Compare</label>
                <a className="link" href={artifactUrl(runId, c.html_path)} target="_blank" rel="noreferrer">Open in tab ↗</a>
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="decision">
        {pick ? (
          <div className="decision__pick">
            <h3>Design {pick.toUpperCase()} · {byId[pick].name} in full</h3>
            <label className="field"><span>Notes for the designer (optional)</span>
              <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. put the pricing teaser higher; B's testimonials idea would fit here" /></label>
            <button className="btn btn--primary" disabled={busy} onClick={() => send({ action: "pick", id: pick, notes })}>Design this direction →</button>
          </div>
        ) : <p className="muted">Choose a sketch to continue, or ask for different directions.</p>}
        <div className="decision__regen">
          <button className="link" onClick={() => setRegen(!regen)} aria-expanded={regen}>None of these? Sketch new directions</button>
          {regen && (
            <div className="regen">
              <label className="field"><span>What&apos;s missing?</span>
                <input value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. our users don't trust finance apps; lead with security" /></label>
              <div className="stepper-row"><span>Directions</span>
                <div className="stepper"><button aria-label="Fewer directions" onClick={() => setCount(Math.max(1, count - 1))}>−</button><output>{count}</output><button aria-label="More directions" onClick={() => setCount(Math.min(10, count + 1))}>+</button></div></div>
              <button className="btn" disabled={busy} onClick={() => send({ action: "regenerate", feedback, candidate_count: count })}>Sketch {count} new direction{count > 1 ? "s" : ""}</button>
            </div>
          )}
        </div>
        {err && <p className="callout callout--error">{err}</p>}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------- Refining */

function Timeline({ state, runId }: { state: RunState; runId: string }) {
  return (
    <ol className="timeline">
      {state.iterations.map(({ iteration, snapshot }, idx) => {
        const prev = idx > 0 ? state.iterations[idx - 1].snapshot : null;
        const open = snapshot.issues.filter((i) => i.status !== "resolved");
        const fixedNow = snapshot.issues.filter((i) => i.status === "resolved" && (!prev || prev.issues.find((p) => p.id === i.id && p.status !== "resolved")));
        const gate = state.gates[iteration];
        return (
          <li key={snapshot.version} className="timeline__item">
            <div className="timeline__shot"><Shot runId={runId} path={snapshot.screenshots.desktop} alt={`Version ${snapshot.version}`} /></div>
            <div className="timeline__body">
              <div className="timeline__head">
                <h3>v{snapshot.version}</h3>
                <span className="score">{snapshot.score?.toFixed(2)}<small>/5</small></span>
                {gate && <span className={`tag tag--${gate.decision}`}>{gate.decision === "continue" ? "Keep improving" : gate.decision === "revert" ? "Reverted" : STOP_REASON[gate.decision] ?? gate.decision}</span>}
              </div>
              {gate?.note && <p className="callout callout--warn">{gate.note}</p>}
              {snapshot.summary && <p className="muted">{snapshot.summary}</p>}
              <AuditBadges checks={snapshot.audit.checks} />
              <div className="timeline__cols">
                <ScoreBars scores={snapshot.scores} previous={prev?.scores} />
                <div>
                  {fixedNow.length > 0 && <><h4>Fixed in this version</h4><ul className="issues">{fixedNow.map((i) => <IssueItem key={i.id} issue={i} fixed />)}</ul></>}
                  <h4>{open.length ? `Open issues (${open.length})` : "No open issues"}</h4>
                  <ul className="issues">{open.map((i) => <IssueItem key={i.id} issue={i} />)}</ul>
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Refining({ state, runId }: { state: RunState; runId: string }) {
  const name = state.briefs.find((b) => b.id === state.picked?.id)?.name;
  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Designing {state.picked?.id.toUpperCase()}{name ? ` · ${name}` : ""}</h2>
        <p className="muted">The designer turns the sketch into a full design. Then a reviewer checks each version against the rubric, a fixer makes targeted edits, and the best version is kept.</p>
      </div>
      <ScoreChart points={state.iterations.map((i) => ({ version: i.snapshot.version, score: i.snapshot.score }))} />
      {!state.iterations.length && <div className="empty"><span className="spinner" /> Designing from the sketch, then the first review…</div>}
      <Timeline state={state} runId={runId} />
    </section>
  );
}

function History({ state, runId }: { state: RunState; runId: string }) {
  if (!state.iterations.length) return null;
  return (
    <details className="history">
      <summary>How the design improved ({state.iterations.length} review{state.iterations.length > 1 ? "s" : ""}) <span className="muted">every issue found and fixed, and why it matters</span></summary>
      <Timeline state={state} runId={runId} />
    </details>
  );
}

/* ---------------------------------------------------------------- Final review */

function FinalReview({ runId, state }: { runId: string; state: RunState }) {
  const f = state.final;
  const [vp, setVp] = useState<"desktop" | "mobile">("desktop");
  const [base, setBase] = useState<"sketch" | "v1">("sketch");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async (body: Record<string, unknown>) => { setBusy(true); try { await api.resume(runId, body); } catch { setBusy(false); } };
  const remaining: Issue[] = f.remaining_issues ?? [];
  const before: string = base === "sketch" && f.sketch ? f.sketch.html_path : f.v1.html_path;
  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Final review</h2>
        <p className="muted">{STOP_REASON[f.stop_reason] ?? f.stop_reason}. Final score <strong>{f.final.score?.toFixed(2)}</strong> (v{f.final.version}).</p>
      </div>
      <div className="seg-row">
        <div className="segmented" role="radiogroup" aria-label="Compare with">
          {(["sketch", "v1"] as const).map((x) => <button key={x} role="radio" aria-checked={base === x} className={base === x ? "is-on" : ""} onClick={() => setBase(x)}>{x === "sketch" ? "Your sketch" : "First design (v1)"}</button>)}
        </div>
        <div className="segmented" role="radiogroup" aria-label="Viewport">
          {(["desktop", "mobile"] as const).map((x) => <button key={x} role="radio" aria-checked={vp === x} className={vp === x ? "is-on" : ""} onClick={() => setVp(x)}>{x === "desktop" ? "Desktop" : "Mobile"}</button>)}
        </div>
      </div>
      <div className="before-after">
        <figure><figcaption>Before · {base === "sketch" ? "the sketch you picked" : "the first full design (v1)"}</figcaption>
          {vp === "desktop" ? <ScaledFrame runId={runId} path={before} title="Before" /> : <div className="mobile-frame"><ScaledFrame runId={runId} path={before} width={375} height={760} title="Before mobile" /></div>}</figure>
        <figure><figcaption>After · v{f.final.version}</figcaption>
          {vp === "desktop" ? <ScaledFrame runId={runId} path={f.final.html_path} title="After" /> : <div className="mobile-frame"><ScaledFrame runId={runId} path={f.final.html_path} width={375} height={760} title="After mobile" /></div>}</figure>
      </div>
      <div className="final-cols">
        <div className="aside-card">
          <ScoreChart points={f.trajectory} />
          <ScoreBars scores={f.final.scores} />
        </div>
        <div className="aside-card">
          <h3>{remaining.length ? `Remaining issues (${remaining.length})` : "No remaining issues"}</h3>
          <ul className="issues">{remaining.map((i) => <IssueItem key={i.id} issue={i} />)}</ul>
          <button className="btn btn--primary btn--block" disabled={busy} onClick={() => send({ action: "approve" })}>Approve and build handoff</button>
          <label className="field"><span>Or request changes</span>
            <textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. make the hero headline shorter; add a pricing teaser" /></label>
          <button className="btn btn--block" disabled={busy || !feedback.trim()} onClick={() => send({ action: "request_changes", feedback })}>Request changes</button>
        </div>
      </div>
      <History state={state} runId={runId} />
    </section>
  );
}

/* -------------------------------------------------------------------- Download */

function Download({ runId, state }: { runId: string; state: RunState }) {
  const last = state.iterations.at(-1)?.snapshot;
  const best = useMemo(() => state.iterations.reduce<Snapshot | undefined>((b, i) => (!b || (i.snapshot.score ?? 0) > (b.score ?? 0) ? i.snapshot : b), undefined), [state.iterations]);
  const cost = state.done?.usage?.cost_usd;
  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Your handoff package is ready</h2>
        <p className="muted">{STOP_REASON[state.done?.stop_reason] ?? state.done?.stop_reason}{state.done?.score != null && <> · final score {Number(state.done.score).toFixed(2)}</>}{cost ? <> · cost ${cost.toFixed(2)}</> : null}</p>
      </div>
      <div className="final-cols">
        <div>{(best ?? last) && <ScaledFrame runId={runId} path="output/index.html" title="Final design" />}</div>
        <div className="aside-card">
          <a className="btn btn--primary btn--block" href={downloadUrl(runId, "zip")}>Download handoff (.zip)</a>
          <div className="dl-list">
            <a className="btn" href={downloadUrl(runId, "html")}>index.html</a>
            <a className="btn" href={downloadUrl(runId, "handoff")}>HANDOFF.md</a>
            <a className="btn" href={downloadUrl(runId, "tokens")}>tokens.json</a>
            <a className="btn" href={downloadUrl(runId, "pdf")}>design.pdf</a>
          </div>
          <h3>Next step</h3>
          <p className="muted">Unzip into an empty folder and tell your coding agent:</p>
          <pre className="code">Build this page in a new Next.js project. Use HANDOFF.md as the spec, index.html as the visual source of truth, and tokens.json for the theme. Compare against screenshots/ at 375, 768 and 1440px.</pre>
          <Link className="link" href="/">Start another brief →</Link>
        </div>
      </div>
      <History state={state} runId={runId} />
    </section>
  );
}
