"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
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
    <div className="page">
      <header className="page-head"><h1>Runs</h1></header>
      {err && <p className="callout callout--error">{err}</p>}
      {runs && !runs.length && <p className="muted">No runs yet. <Link className="link" href="/">Start one</Link>.</p>}
      <ul className="run-list">
        {runs?.map((r) => (
          <li key={r.run_id}>
            <Link href={`/runs/${r.run_id}`}>
              <span className="run-list__prompt">{r.prompt || "(no prompt)"}</span>
              <span className="muted mono">{r.run_id}</span>
              <span className={`tag tag--${r.status}`}>{STATUS[r.status] ?? r.status}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
