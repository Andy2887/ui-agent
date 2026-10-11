"use client";
// Screen 7 — what the agent remembers (§9), with reset.
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const [mem, setMem] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api.memory().then(setMem).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const reset = async (what: string) => { await api.resetMemory(what); load(); };
  const counts = Object.entries<any>(mem?.taste?.counts ?? {}).sort((a, b) => (b[1].picked ?? 0) - (a[1].picked ?? 0));
  return (
    <div className="page page--narrow">
      <header className="page-head">
        <h1>Memory</h1>
        <p>What the agent has learned from your runs. It only remembers explicit signals: the sketches you pick and pass over, your notes, and recurring issues.</p>
      </header>
      {err && <p className="callout callout--error">{err}</p>}
      <section className="aside-card">
        <div className="section-bar"><h2 className="h2">Your taste</h2><button className="btn" onClick={() => reset("taste")}>Reset taste</button></div>
        {counts.length ? <p className="muted">Directions leaning toward what you picked get a &ldquo;Based on your past picks&rdquo; slot in future runs.</p> : <p className="muted">Nothing yet.</p>}
        {counts.length > 0 && (
          <table className="table">
            <thead><tr><th>Attribute</th><th>Picked</th><th>Passed over</th></tr></thead>
            <tbody>{counts.map(([k, v]) => <tr key={k}><td className="mono">{k}</td><td>{v.picked ?? 0}</td><td>{v.rejected ?? 0}</td></tr>)}</tbody>
          </table>
        )}
        {mem?.taste?.notes?.length > 0 && <><h3>Your notes</h3><ul>{mem.taste.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul></>}
      </section>
      <section className="aside-card">
        <div className="section-bar"><h2 className="h2">Lessons learned</h2><button className="btn" onClick={() => reset("lessons")}>Reset lessons</button></div>
        <p className="muted">Recurring problems. A lesson becomes a pre-flight checklist item for the designer after it shows up in 3 runs.</p>
        <table className="table">
          <thead><tr><th>Issue</th><th>Runs</th><th>Status</th></tr></thead>
          <tbody>{(mem?.lessons ?? []).map((l: any) => <tr key={l.id}><td className="mono">{l.id}</td><td>{l.count}</td><td>{l.promoted ? "In checklist" : "Watching"}</td></tr>)}</tbody>
        </table>
      </section>
      <section className="aside-card">
        <div className="section-bar"><h2 className="h2">Run history</h2><button className="btn" onClick={() => reset("runs")}>Clear</button></div>
        <table className="table">
          <thead><tr><th>Brief</th><th>Score</th><th>Stopped</th></tr></thead>
          <tbody>{(mem?.runs ?? []).map((r: any) => <tr key={r.id}><td>{r.prompt}</td><td>{r.final_score ?? "–"}</td><td>{r.stop_reason}</td></tr>)}</tbody>
        </table>
      </section>
      <button className="btn btn--danger" onClick={() => reset("all")}>Reset all memory</button>
    </div>
  );
}
