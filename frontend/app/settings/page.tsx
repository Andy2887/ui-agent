"use client";
// Screen 7 — what the agent remembers (§9), with reset.
import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const [mem, setMem] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api.memory().then(setMem).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const reset = async (what: string) => { await api.resetMemory(what); load(); };
  const counts = Object.entries<any>(mem?.taste?.counts ?? {}).sort((a, b) => (b[1].picked ?? 0) - (a[1].picked ?? 0));
  const lessons: any[] = mem?.lessons ?? [];
  const runs: any[] = mem?.runs ?? [];
  return (
    <div className="page page--narrow">
      <header className="page-head">
        <span className="eyebrow">Memory</span>
        <h1>What the agent has learned</h1>
        <p>It only remembers explicit signals: the sketches you pick and pass over, your notes, and recurring issues.</p>
      </header>
      {err && <div className="callout callout--error" role="alert"><Icon name="alert" /><div>{err}</div></div>}
      <section className="card">
        <div className="card__head">
          <h2 className="h2">Your taste</h2>
          <button className="btn btn--sm" onClick={() => reset("taste")}>Reset taste</button>
          <p className="muted">{counts.length ? <>Directions leaning toward what you picked get a &ldquo;Based on your past picks&rdquo; slot in future runs.</> : "Nothing yet. Pick a sketch in a run and it shows up here."}</p>
        </div>
        {counts.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Attribute</th><th className="num">Picked</th><th className="num">Passed over</th></tr></thead>
              <tbody>{counts.map(([k, v]) => <tr key={k}><td className="mono">{k}</td><td className="num">{v.picked ?? 0}</td><td className="num">{v.rejected ?? 0}</td></tr>)}</tbody>
            </table>
          </div>
        )}
        {mem?.taste?.notes?.length > 0 && <><h4>Your notes</h4><ul>{mem.taste.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul></>}
      </section>
      <section className="card">
        <div className="card__head">
          <h2 className="h2">Lessons learned</h2>
          <button className="btn btn--sm" onClick={() => reset("lessons")}>Reset lessons</button>
          <p className="muted">Recurring problems. A lesson becomes a pre-flight checklist item for the designer after it shows up in 3 runs.</p>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Issue</th><th className="num">Runs</th><th>Status</th></tr></thead>
            <tbody>
              {lessons.map((l) => <tr key={l.id}><td className="mono">{l.id}</td><td className="num">{l.count}</td>
                <td><span className={`tag tag--dot ${l.promoted ? "tag--done" : ""}`}>{l.promoted ? "In checklist" : "Watching"}</span></td></tr>)}
              {!lessons.length && <tr><td colSpan={3} className="table-empty">No lessons yet</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <div className="card__head">
          <h2 className="h2">Run history</h2>
          <button className="btn btn--sm" onClick={() => reset("runs")}>Clear</button>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Brief</th><th className="num">Score</th><th>Stopped</th></tr></thead>
            <tbody>
              {runs.map((r) => <tr key={r.id}><td>{r.prompt}</td><td className="num">{r.final_score ?? "–"}</td><td className="muted">{r.stop_reason}</td></tr>)}
              {!runs.length && <tr><td colSpan={3} className="table-empty">No finished runs yet</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card danger-zone">
        <div>
          <h2 className="h2">Reset everything</h2>
          <p className="muted">Forget your taste, lessons and run history. Runs themselves stay on disk.</p>
        </div>
        <button className="btn btn--danger" onClick={() => reset("all")}>Reset all memory</button>
      </section>
    </div>
  );
}
