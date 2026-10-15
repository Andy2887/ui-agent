"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api";

const STATUS: Record<string, string> = {
  running: "Running", waiting_kickoff: "Questions for you", waiting_gallery: "Waiting for your pick",
  waiting_approval: "Waiting for approval",
  done: "Done", error: "Error",
};

export default function RunsPage() {
  const [runs, setRuns] = useState<{ run_id: string; prompt: string; status: string }[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.listRuns().then(setRuns).catch((e) => setErr(e.message)); }, []);
  return (
    <div className="page page--narrow">
      <header className="page-head">
        <span className="eyebrow">{runs ? `${runs.length} run${runs.length === 1 ? "" : "s"}` : "History"}</span>
        <h1>Runs</h1>
      </header>
      {err && <div className="callout callout--error" role="alert"><Icon name="alert" /><div>{err}</div></div>}
      {!runs && !err && <div className="skeleton" style={{ height: 216 }} aria-label="Loading runs" />}
      {runs && !runs.length && (
        <div className="empty">
          <h2 className="h2">No runs yet</h2>
          <p>Brief the designer on a problem and it will sketch a few directions for you to pick from.</p>
          <Link className="btn btn--primary" href="/"><Icon name="plus" />New brief</Link>
        </div>
      )}
      {runs && runs.length > 0 && (
        <ul className="run-list">
          {runs.map((r) => (
            <li key={r.run_id}>
              <Link href={`/runs/${r.run_id}`}>
                <span className="run-list__prompt">{r.prompt || "(no prompt)"}</span>
                <span className="mono run-list__id">{r.run_id}</span>
                <span className={`tag tag--dot tag--${r.status}`}>{STATUS[r.status] ?? r.status}</span>
                <Icon name="chevronRight" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
