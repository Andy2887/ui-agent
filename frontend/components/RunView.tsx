"use client";
// Screens 2–7: Kickoff, Sketching, Review sketches, Designing & refining (page by page), Final review, Download — all driven by the run's SSE events.
import Link from "next/link";
import { useEffect, useState, type CSSProperties } from "react";
import { api, artifactUrl, downloadUrl, eventsUrl } from "@/lib/api";
import { SLOT_LABEL, STOP_REASON } from "@/lib/logic";
import type { Brief, DesignBrief, FinalApproval, FinalPage, FlowPlan, Issue, KickoffQuestion, PagePlan, RunEvent, Sketch, SketchReview, Snapshot } from "@/lib/types";
import { AgentGraph, initialTrack, trackAgent, type AgentTrack } from "./AgentGraph";
import { Icon } from "./Icon";
import { RefineHelix } from "./RefineHelix";
import { AuditBadges, IssueItem, ScaledFrame, ScoreBars, ScoreChart, SketchView, Shot } from "./RunParts";

type PageProgress = { status: "queued" | "designing" | "refining" | "done" | "skipped"; score?: number | null; version?: number; stop?: string | null };
type Iteration = { pageId: string; iteration: number; snapshot: Snapshot };

type RunState = {
  status: string; error?: string; mock?: boolean; request?: any; productName?: string;
  intake?: DesignBrief;
  kickoff?: { intake: DesignBrief; questions: KickoffQuestion[] };
  direction?: Brief; repairs: string[];
  sketches: Record<string, { sketch?: Sketch; started: boolean }>;
  review?: SketchReview;
  approved: boolean;
  final?: FinalApproval;
  currentPage?: string;
  progress: Record<string, PageProgress>;
  iterations: Iteration[];
  gates: Record<string, { decision: string; note?: string }>; // `${page}:${iteration}`
  activity: string;
  agent: AgentTrack;
  pageAgents: Record<string, AgentTrack>; // design stage: one pipeline track per page, since pages run in parallel
  pageActivity: Record<string, string>;
  done?: any;
};

const initial: RunState = { status: "connecting", repairs: [], sketches: {}, approved: false, progress: {}, iterations: [], gates: {}, activity: "", agent: initialTrack, pageAgents: {}, pageActivity: {} };
const pageStart: AgentTrack = { visited: ["intake", "planner", "sketch"] };

function reduce(s: RunState, e: RunEvent): RunState {
  const next = reduceEvent(s, e);
  // Once the sketches are approved, a page's events move only that page's graph, so parallel pages don't fight over one.
  const pid: string | undefined = s.approved ? e.page_id : undefined;
  if (pid) {
    const track = trackAgent(e.type === "page_started" ? pageStart : s.pageAgents[pid] ?? pageStart, e);
    return { ...next, pageAgents: { ...next.pageAgents, [pid]: track },
             pageActivity: next.activity === s.activity ? next.pageActivity : { ...next.pageActivity, [pid]: next.activity } };
  }
  const agent = trackAgent(s.agent, e);
  return agent === next.agent ? next : { ...next, agent };
}

function pageName(s: RunState, id?: string | null) {
  return s.intake?.pages.find((p) => p.id === id)?.name ?? id ?? "";
}

function reduceEvent(s: RunState, e: RunEvent): RunState {
  const on = e.page_id ? `${pageName(s, e.page_id)}: ` : "";
  switch (e.type) {
    case "status":
      return { ...s, status: e.status, error: e.error ?? (e.status === "error" ? s.error : undefined), mock: e.mock ?? s.mock, request: e.request ?? s.request,
               done: e.status === "done" ? e : s.done };
    case "intake": return { ...s, intake: e.intake, productName: e.intake?.product_name, activity: "Planning the direction…" };
    case "kickoff_answered": return { ...s, activity: "Updating the brief with your answers…" };
    case "kickoff_skipped": return { ...s, activity: "Planning the direction…" };
    case "direction": {
      const sketches: RunState["sketches"] = {};
      for (const p of s.intake?.pages ?? []) sketches[p.id] = { started: false };
      return { ...s, direction: e.direction, repairs: e.repairs ?? [], sketches, review: undefined, activity: `Sketching ${Object.keys(sketches).length} pages…` };
    }
    case "sketch_started": return { ...s, sketches: { ...s.sketches, [e.page_id]: { ...s.sketches[e.page_id], started: true } } };
    case "sketch_ready": return { ...s, sketches: { ...s.sketches, [e.page_id]: { sketch: e.sketch, started: true } } };
    case "interrupt":
      if (e.kind === "kickoff") return { ...s, kickoff: e.payload, activity: "" };
      return e.kind === "sketch_review" ? { ...s, review: e.payload, activity: "" } : { ...s, final: e.payload, activity: "" };
    case "revising": return { ...s, review: undefined, activity: "Revising the direction and sketches with your feedback…" };
    case "sketches_approved": {
      const progress: RunState["progress"] = {};
      for (const id of e.pages as string[]) progress[id] = { status: "queued" };
      return { ...s, approved: true, progress, iterations: [], gates: {}, pageAgents: {}, pageActivity: {}, activity: "Designing the first page…" };
    }
    case "page_started": return { ...s, currentPage: e.page_id, progress: { ...s.progress, [e.page_id]: { ...s.progress[e.page_id], status: e.revisit ? "refining" : "designing" } },
                                  activity: `Page ${e.index} of ${e.total}: ${e.revisit ? "applying your changes to" : "designing"} ${e.name}…` };
    case "design_ready": return { ...s, progress: { ...s.progress, [e.page_id]: { ...s.progress[e.page_id], status: "refining" } }, activity: `${on}starting refinement…` };
    case "style_locked": return { ...s, activity: "Locking the design system from the first page…" };
    case "render_started": return { ...s, activity: `${on}rendering v${e.version} at 375, 768 and 1440px…` };
    case "review_started": return { ...s, activity: `${on}reviewing v${e.version} against the rubric…` };
    case "execute_started": return { ...s, activity: `${on}fixing ${e.issues.length} issue${e.issues.length === 1 ? "" : "s"} → v${e.version}…` };
    case "iteration": {
      const pageId = e.page_id ?? e.snapshot.page_id;
      return { ...s, iterations: [...s.iterations.filter((i) => !(i.pageId === pageId && i.snapshot.version === e.snapshot.version)), { pageId, iteration: e.iteration, snapshot: e.snapshot }] };
    }
    case "gate": return { ...s, gates: { ...s.gates, [`${e.page_id}:${e.iteration}`]: { decision: e.decision, note: e.note } } };
    case "page_done": return { ...s, progress: { ...s.progress, [e.page_id]: { status: "done", score: e.score, version: e.version, stop: e.stop_reason } } };
    case "page_skipped": return { ...s, progress: { ...s.progress, [e.page_id]: { status: "skipped", stop: e.reason } } };
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

  const phase = state.status === "done" ? 4 : state.final ? 3 : state.approved ? 2 : state.direction || state.review ? 1 : 0;
  const brief = state.request?.brief;

  return (
    <div className="page">
      <header className="run-head">
        <div className="run-head__title">
          <span className="eyebrow">Run <span className="num">{runId}</span></span>
          <h1>{brief?.product_name || state.productName || "Design run"}</h1>
          <p className="clamp">{brief?.problem ?? state.request?.prompt}</p>
        </div>
        <Steps phase={phase} />
      </header>
      {state.mock && <p className="callout"><Icon name="sparkle" />Mock mode: sketches, designs, reviews and fixes come from offline stand-ins, not Claude.</p>}
      {lost && state.status !== "done" && <p className="callout callout--warn" role="status"><span className="spinner" />Connection lost. Reconnecting…</p>}
      {state.status === "error" && <div className="callout callout--error" role="alert"><Icon name="alert" /><div><strong>The run stopped with an error.</strong><pre>{state.error}</pre></div></div>}
      {state.status === "running" && phase !== 2 && <AgentGraph track={state.agent} caption={state.activity} />}

      {phase === 0 && state.status === "waiting_kickoff" && state.kickoff && <Kickoff runId={runId} kickoff={state.kickoff} />}
      {phase === 1 && state.status === "waiting_sketches" && state.review && <ReviewSketches runId={runId} review={state.review} />}
      {phase === 1 && state.status !== "waiting_sketches" && <Sketching state={state} />}
      {phase === 2 && <Refining state={state} runId={runId} />}
      {phase === 3 && state.final && <FinalReview runId={runId} state={state} final={state.final} />}
      {phase === 4 && <Download runId={runId} state={state} />}
    </div>
  );
}

/* --------------------------------------------------------------- Design brief */

/** The flows as the designer mapped them onto pages: one row per flow, one stop per page. */
function FlowMap({ flows, pages }: { flows: FlowPlan[]; pages: PagePlan[] }) {
  const name = (id: string) => pages.find((p) => p.id === id)?.name ?? id;
  return (
    <ol className="flow-map">
      {flows.map((f, i) => (
        <li key={i}>
          <span className="flow-map__name">{f.name}</span>
          <ol className="flow-map__steps">
            {f.steps.map((st, j) => <li key={j} title={st.action}><span className="flow-map__page">{name(st.page)}</span><span className="flow-map__action">{st.action}</span></li>)}
          </ol>
        </li>
      ))}
    </ol>
  );
}

function DesignBriefCard({ brief, open }: { brief: DesignBrief; open?: boolean }) {
  return (
    <details className="design-brief aside-card" open={open}>
      <summary>The design brief <span className="muted">how the designer read your request, and the pages it needs</span></summary>
      <dl>
        <dt>Problem</dt><dd>{brief.problem}</dd>
        <dt>Users</dt><dd>{brief.audience}</dd>
        <dt>They need to</dt><dd><ul>{brief.user_needs.map((n) => <li key={n}>{n}</li>)}</ul></dd>
        <dt>Pages</dt><dd><ul>{brief.pages.map((p) => <li key={p.id}><strong>{p.name}</strong> <span className="mono muted">{p.file}</span>: {p.purpose}</li>)}</ul></dd>
        <dt>Flows</dt><dd><FlowMap flows={brief.flows} pages={brief.pages} /></dd>
        {(brief.not_designed?.length ?? 0) > 0 && <><dt>Not designed</dt><dd>Over the 6-page limit: {brief.not_designed!.join(", ")}</dd></>}
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
          <button className="btn btn--primary" disabled={busy || !answered} onClick={() => send(answers)}>Continue to sketches<Icon name="arrowRight" /></button>
          <button className="link link--muted" disabled={busy} onClick={() => send({})}>Skip, use your best judgement</button>
        </div>
        {err && <div className="callout callout--error" role="alert"><Icon name="alert" /><div>{err}</div></div>}
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

const RADIUS: Record<string, [string, string]> = { sharp: ["2px", "3px"], soft: ["8px", "12px"], rounded: ["999px", "18px"] }; // [button, card]
const PAD: Record<string, string> = { compact: "12px", balanced: "16px", airy: "22px" };
const SWATCHES = ["bg", "surface", "primary", "accent", "muted", "text"] as const;

/** A style tile: the direction's design system applied to a small hero sample and a card, like a designer's mood sheet. */
function StyleTile({ brief, action, headline }: { brief: Brief; action?: string; headline?: string }) {
  useGoogleFonts([brief.heading_font, brief.body_font]);
  const p = brief.palette;
  const [btnR, cardR] = RADIUS[brief.shape] ?? RADIUS.soft;
  const vars = {
    "--t-bg": p.bg, "--t-surface": p.surface, "--t-text": p.text, "--t-muted": p.muted, "--t-primary": p.primary,
    "--t-on-primary": p.on_primary, "--t-accent": p.accent, "--t-border": p.border,
    "--t-heading": `"${brief.heading_font}", system-ui, sans-serif`, "--t-body": `"${brief.body_font}", system-ui, sans-serif`,
    "--t-btn-r": btnR, "--t-card-r": cardR, "--t-pad": PAD[brief.density] ?? PAD.balanced,
  } as CSSProperties;
  return (
    <figure className="tile" style={vars} aria-label={`Design system: ${brief.mood.join(", ")}`}>
      <div className="tile__hero">
        <span className="tile__eyebrow">{brief.mood.join(" · ")}</span>
        <p className="tile__headline">{headline ?? brief.name}</p>
        <p className="tile__lead">{brief.description}</p>
        <div className="tile__actions">
          <span className="tile__btn tile__btn--primary">{action || "Get started"}</span>
          <span className="tile__btn">Learn more</span>
        </div>
      </div>
      <div className="tile__card">
        <span className="tile__tag">Signature</span>
        <p className="tile__card-text">{brief.signature_element}</p>
      </div>
      <div className="tile__swatches">
        {SWATCHES.map((k) => <span key={k} title={`${k} ${p[k]}`}><i style={{ background: p[k] }} />{k}</span>)}
      </div>
      <figcaption className="tile__meta">{brief.reference_style} · {brief.heading_font} / {brief.body_font} · {brief.theme} · {brief.density} · {brief.shape}</figcaption>
    </figure>
  );
}

/** The direction: the bet on solving the problem (left) and the design system every page will share (right). */
function DirectionCard({ brief, action, productName }: { brief: Brief; action?: string; productName?: string }) {
  return (
    <div className="direction">
      <div className="direction__text">
        <div className="cand__head"><h3>{brief.name}</h3><span className="tag">{SLOT_LABEL[brief.slot] ?? brief.slot}</span></div>
        <p className="cand__concept">{brief.concept}</p>
        <p className="cand__tradeoff"><strong>Trade-off:</strong> {brief.tradeoff}</p>
        <p className="muted"><strong>Layout:</strong> {brief.layout_archetype}</p>
      </div>
      <StyleTile brief={brief} action={action} headline={productName || brief.name} />
    </div>
  );
}

/* ------------------------------------------------------------------- Sketching */

function Sketching({ state }: { state: RunState }) {
  if (!state.direction || !state.intake) return null;
  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Sketching {state.intake.pages.length} page{state.intake.pages.length > 1 ? "s" : ""}</h2>
        {state.repairs.length > 0 && <p className="note">Contrast adjusted in the proposed palette: {state.repairs.join("; ")}</p>}
      </div>
      <DirectionCard brief={state.direction} action={state.intake.pages[0]?.primary_action} productName={state.productName} />
      <div className="grid grid--cards">
        {state.intake.pages.map((p) => {
          const c = state.sketches[p.id];
          return (
            <article key={p.id} className="cand">
              <div className="cand__media">
                {c?.sketch?.text ? <SketchView text={c.sketch.text} label={`${p.name} sketch`} />
                  : c?.sketch?.error ? <div className="shot shot--empty">Sketch failed: {c.sketch.error}</div>
                  : <div className="shot shot--loading"><span className="spinner" />{c?.started ? "Sketching…" : "Queued"}</div>}
              </div>
              <div className="cand__body"><PageHead page={p} /></div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function PageHead({ page }: { page: PagePlan | FinalPage }) {
  return (
    <>
      <div className="cand__head"><h3>{page.name}</h3><span className="tag mono">{page.file}</span></div>
      <p>{page.purpose}</p>
    </>
  );
}

/** Tabs that pick one page. Shared by the sketch review and the final review. */
function PageTabs({ pages, value, onChange, badge }: { pages: { id: string; name: string }[]; value: string; onChange: (id: string) => void; badge?: (id: string) => string | null }) {
  return (
    <div className="segmented page-tabs" role="tablist" aria-label="Pages">
      {pages.map((p, i) => (
        <button key={p.id} role="tab" aria-selected={value === p.id} className={value === p.id ? "is-on" : ""} onClick={() => onChange(p.id)}>
          <span className="page-tabs__n">{i + 1}</span>{p.name}{badge?.(p.id) && <span className="page-tabs__badge">{badge(p.id)}</span>}
        </button>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- Review sketches */

function ReviewSketches({ runId, review }: { runId: string; review: SketchReview }) {
  const [page, setPage] = useState(review.pages[0]?.id ?? "");
  const [notes, setNotes] = useState("");
  const [revise, setRevise] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const current = review.pages.find((p) => p.id === page) ?? review.pages[0];
  const failed = review.pages.filter((p) => p.error);

  const send = async (body: Record<string, unknown>) => {
    setBusy(true); setErr(null);
    try { await api.resume(runId, body); } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Review the direction and the sketches</h2>
        <p className="muted">One direction for the whole site: the bet on solving the problem, and the design system every page will share. Below it is a sketch of every page. Sketches are text wireframes on purpose: judge the structure, the content and how each page leads to the next.</p>
      </div>
      <DesignBriefCard brief={review.design_brief} />
      <DirectionCard brief={review.direction} action={review.pages[0]?.primary_action} productName={review.design_brief.product_name} />

      <h3 className="h3 choice-head">How users move through the site</h3>
      <FlowMap flows={review.design_brief.flows} pages={review.design_brief.pages} />

      <h3 className="h3 choice-head">Page sketches</h3>
      <PageTabs pages={review.pages} value={current.id} onChange={setPage} badge={(id) => (review.pages.find((p) => p.id === id)?.error ? "failed" : null)} />
      <div className="viewer-panel page-view">
        <div className="page-view__head">
          <PageHead page={current} />
          {current.links_to.length > 0 && <p className="muted">Links to: {current.links_to.map((l) => review.pages.find((p) => p.id === l)?.name ?? l).join(", ")}</p>}
        </div>
        {current.error ? <div className="shot shot--empty">Sketch failed: {current.error}. The designer will design this page from its plan.</div>
          : <SketchView text={current.sketch} label={`${current.name} sketch`} />}
      </div>

      <div className="decision">
        <div className="decision__pick">
          <label className="field"><span>Notes for the designer (optional)</span>
            <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. put the pricing teaser higher on the home page; keep the sign-up form to one field" /></label>
          <button className="btn btn--primary" disabled={busy} onClick={() => send({ action: "approve", notes })}>
            {busy && !revise ? <><span className="spinner" />Starting…</> : <>Approve and design {review.pages.length} page{review.pages.length > 1 ? "s" : ""}<Icon name="arrowRight" /></>}</button>
          {failed.length > 0 && <p className="note">{failed.length} sketch{failed.length > 1 ? "es" : ""} failed; those pages are designed from their plan.</p>}
        </div>
        <div className="decision__regen">
          <button className="link link--muted" onClick={() => setRevise(!revise)} aria-expanded={revise}>Not right? Ask for changes</button>
          {revise && (
            <div className="regen">
              <label className="field"><span>What should change?</span>
                <textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. our users don't trust finance apps, lead with security; or: try a completely different look" /></label>
              <button className="btn" disabled={busy || !feedback.trim()} onClick={() => send({ action: "revise", feedback })}>Revise the direction and sketches</button>
            </div>
          )}
        </div>
        {err && <div className="callout callout--error" role="alert"><Icon name="alert" /><div>{err}</div></div>}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------- Refining */

function Timeline({ state, runId, pageId }: { state: RunState; runId: string; pageId: string }) {
  const items = state.iterations.filter((i) => i.pageId === pageId);
  return (
    <ol className="timeline">
      {items.map(({ iteration, snapshot }, idx) => {
        const prev = idx > 0 ? items[idx - 1].snapshot : null;
        const open = snapshot.issues.filter((i) => i.status !== "resolved");
        const fixedNow = snapshot.issues.filter((i) => i.status === "resolved" && (!prev || prev.issues.find((p) => p.id === i.id && p.status !== "resolved")));
        const gate = state.gates[`${pageId}:${iteration}`];
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

const PROGRESS_LABEL: Record<PageProgress["status"], string> = { queued: "Queued", designing: "Designing", refining: "Refining", done: "Done", skipped: "Skipped" };

function PageProgressList({ state, selected, onSelect }: { state: RunState; selected: string; onSelect: (id: string) => void }) {
  const pages = state.intake?.pages ?? [];
  return (
    <ol className="page-progress">
      {pages.map((p, i) => {
        const pr = state.progress[p.id] ?? { status: "queued" };
        const busy = pr.status === "designing" || pr.status === "refining";
        return (
          <li key={p.id}>
            <button className={selected === p.id ? "is-on" : ""} aria-pressed={selected === p.id} onClick={() => onSelect(p.id)} disabled={pr.status === "queued"}>
              <span className="page-tabs__n">{i + 1}</span>
              <span className="page-progress__name">{p.name}{i === 0 && <span className="muted"> · sets the design system</span>}</span>
              <span className={`tag tag--${pr.status === "done" ? (pr.stop === "pass" ? "pass" : "plateau") : pr.status === "skipped" ? "budget" : busy ? "running" : ""}`}>
                {busy && <span className="spinner" />}{PROGRESS_LABEL[pr.status]}{pr.status === "done" && pr.score != null ? ` · ${pr.score.toFixed(2)}` : ""}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function Refining({ state, runId }: { state: RunState; runId: string }) {
  const [picked, setPicked] = useState<string | null>(null);
  // Several pages refine at once after the key page; follow the first busy one unless the PM picked a page.
  const busy = state.intake?.pages.find((p) => ["designing", "refining"].includes(state.progress[p.id]?.status ?? ""))?.id;
  const pageId = picked ?? busy ?? state.currentPage ?? state.intake?.pages[0]?.id ?? "";
  const laps = state.iterations.filter((i) => i.pageId === pageId)
    .map((i) => ({ version: i.snapshot.version, score: i.snapshot.score, decision: state.gates[`${pageId}:${i.iteration}`]?.decision }));
  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Designing {state.intake?.pages.length ?? ""} pages{state.direction ? ` in ${state.direction.name}` : ""}</h2>
        <p className="muted">The first page sets the design system, so it goes first. Then every other page is designed at the same time, reusing its tokens, header, footer and components. For each page, a reviewer checks every version against the rubric, a fixer makes targeted edits, and the best version is kept. Pick a page to follow it.</p>
      </div>
      <PageProgressList state={state} selected={pageId} onSelect={setPicked} />
      <h3 className="h3 choice-head">{pageName(state, pageId)}</h3>
      {["designing", "refining"].includes(state.progress[pageId]?.status ?? "") &&
        <RefineHelix track={state.pageAgents[pageId] ?? pageStart} caption={state.pageActivity[pageId] ?? ""} laps={laps} />}
      <ScoreChart points={laps} />
      <Timeline state={state} runId={runId} pageId={pageId} />
    </section>
  );
}

function History({ state, runId }: { state: RunState; runId: string }) {
  const pages = (state.intake?.pages ?? []).filter((p) => state.iterations.some((i) => i.pageId === p.id));
  if (!pages.length) return null;
  return (
    <details className="history">
      <summary>How the pages improved ({state.iterations.length} review{state.iterations.length > 1 ? "s" : ""}) <span className="muted">every issue found and fixed, and why it matters</span></summary>
      {pages.map((p) => <div key={p.id}><h3 className="h3 choice-head">{p.name}</h3><Timeline state={state} runId={runId} pageId={p.id} /></div>)}
    </details>
  );
}

/* ---------------------------------------------------------------- Final review */

function FinalReview({ runId, state, final }: { runId: string; state: RunState; final: FinalApproval }) {
  const [pageId, setPageId] = useState(final.pages[0]?.id ?? "");
  const [vp, setVp] = useState<"desktop" | "mobile">("desktop");
  const [feedback, setFeedback] = useState("");
  const [target, setTarget] = useState<"page" | "all">("page");
  const [busy, setBusy] = useState(false);
  const send = async (body: Record<string, unknown>) => { setBusy(true); try { await api.resume(runId, body); } catch { setBusy(false); } };
  const page = final.pages.find((p) => p.id === pageId) ?? final.pages[0];
  const remaining: Issue[] = page.remaining_issues ?? [];
  const live = `${final.site_dir}/${page.file}`; // site/ holds every page, so links inside the preview work
  const frame = (path: string, title: string) => vp === "desktop" ? <ScaledFrame runId={runId} path={path} title={title} />
    : <div className="mobile-frame"><ScaledFrame runId={runId} path={path} width={375} height={760} title={`${title} mobile`} /></div>;
  const scored = final.pages.filter((p) => p.final?.score != null);
  const mean = scored.length ? scored.reduce((a, p) => a + (p.final!.score ?? 0), 0) / scored.length : null;

  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Final review</h2>
        <p className="muted">{final.pages.length} pages{mean != null && <> · mean score <strong>{mean.toFixed(2)}</strong></>}. The previews are live: click a link or button to move between pages, as a user would.</p>
      </div>
      <FlowMap flows={final.flows} pages={final.pages.map((p) => ({ ...p, page_type: "", primary_action: "", sections: [], links_to: [] }))} />
      {final.not_designed.length > 0 && <p className="note">Not designed (over the 6-page limit): {final.not_designed.join(", ")}.</p>}

      <PageTabs pages={final.pages} value={page.id} onChange={setPageId} badge={(id) => {
        const p = final.pages.find((x) => x.id === id);
        return p?.skipped ? "skipped" : p?.final?.score != null ? p.final.score.toFixed(1) : null;
      }} />
      {page.skipped || !page.final || !page.v1 ? (
        <div className="callout callout--warn"><Icon name="alert" /><div>{page.name} wasn&apos;t designed: the run reached its cost budget first. Request changes on this page to try again.</div></div>
      ) : (
        <>
          <div className="seg-row">
            <div className="segmented" role="radiogroup" aria-label="Viewport">
              {(["desktop", "mobile"] as const).map((x) => <button key={x} role="radio" aria-checked={vp === x} className={vp === x ? "is-on" : ""} onClick={() => setVp(x)}>{x === "desktop" ? "Desktop" : "Mobile"}</button>)}
            </div>
            <a className="link" href={artifactUrl(runId, live)} target="_blank" rel="noreferrer">Open the site in a new tab<Icon name="arrowRight" size={14} /></a>
          </div>
          <figure className="final-preview"><figcaption><b>Final</b>v{page.final.version}, {STOP_REASON[page.stop_reason ?? ""]?.toLowerCase() ?? page.stop_reason}</figcaption>
            {frame(live, page.name)}</figure>
        </>
      )}
      <div className="final-cols final-cols--single">
        <div className="aside-card">
          <h3>{remaining.length ? `${page.name}: remaining issues (${remaining.length})` : `${page.name}: no remaining issues`}</h3>
          <ul className="issues">{remaining.map((i) => <IssueItem key={i.id} issue={i} />)}</ul>
          <button className="btn btn--primary btn--block" disabled={busy} onClick={() => send({ action: "approve" })}><Icon name="check" />Approve all pages and build handoff</button>
          <div className="divider" />
          <label className="field"><span>Or request changes</span>
            <textarea rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. make the hero headline shorter; add a pricing teaser" /></label>
          <div className="segmented" role="radiogroup" aria-label="Apply the change to">
            <button role="radio" aria-checked={target === "page"} className={target === "page" ? "is-on" : ""} onClick={() => setTarget("page")}>{page.name} only</button>
            <button role="radio" aria-checked={target === "all"} className={target === "all" ? "is-on" : ""} onClick={() => setTarget("all")}>All pages</button>
          </div>
          <button className="btn btn--block" disabled={busy || !feedback.trim()}
            onClick={() => send({ action: "request_changes", feedback, page_id: target === "all" ? "all" : page.id })}>Request changes</button>
        </div>
      </div>
      <History state={state} runId={runId} />
    </section>
  );
}

/* -------------------------------------------------------------------- Download */

function Download({ runId, state }: { runId: string; state: RunState }) {
  const cost = state.done?.usage?.cost_usd;
  const pages = (state.intake?.pages ?? []).filter((p) => state.progress[p.id]?.status === "done");
  return (
    <section>
      <div className="section-bar">
        <h2 className="h2">Your handoff package is ready</h2>
        <p className="muted">{pages.length} page{pages.length === 1 ? "" : "s"}{state.done?.score != null && <> · mean score {Number(state.done.score).toFixed(2)}</>}{cost ? <> · cost ${cost.toFixed(2)}</> : null}</p>
      </div>
      <div className="final-cols">
        <div><ScaledFrame runId={runId} path="output/index.html" title="Final site: home page" /></div>
        <div className="aside-card">
          <a className="btn btn--primary btn--block" href={downloadUrl(runId, "zip")}><Icon name="download" />Download handoff (.zip)</a>
          <div className="dl-list">
            {([["handoff", "HANDOFF.md"], ["flows", "FLOWS.md"], ["tokens", "tokens.json"], ["pdf", "index.pdf"]] as const).map(([kind, name]) =>
              <a key={kind} className="btn btn--sm btn--file" href={downloadUrl(runId, kind)}><Icon name="file" size={14} />{name}</a>)}
          </div>
          <h3>Pages</h3>
          <ul className="page-files">
            {pages.map((p) => <li key={p.id}><a className="link" href={artifactUrl(runId, `output/${p.file}`)} target="_blank" rel="noreferrer"><span className="mono">{p.file}</span> {p.name}</a></li>)}
          </ul>
          <div className="divider" />
          <h3>Next step</h3>
          <p className="muted">Unzip into an empty folder and tell your coding agent:</p>
          <pre className="code">Build this site in a new Next.js project, one route per HTML file. Use HANDOFF.md as the spec, the HTML files as the visual source of truth, tokens.json for the theme and FLOWS.md for how the pages link. Compare each page against screenshots/&lt;page&gt;/ at 375, 768 and 1440px.</pre>
          <Link className="link" href="/">Start another brief<Icon name="arrowRight" size={14} /></Link>
        </div>
      </div>
      <History state={state} runId={runId} />
    </section>
  );
}
