"use client";
// Screen 1 — Brief (§5): the PM describes the problem and the users. The look is the designer's job.
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ProductBrief } from "@/lib/types";

const MIN_COUNT = 1;
const MAX_COUNT = 10;

export function BriefScreen() {
  const router = useRouter();
  const [brief, setBrief] = useState<ProductBrief>({ problem: "", audience: "", product_name: "", goal: "", context: "" });
  const [count, setCount] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mock, setMock] = useState(false);

  useEffect(() => {
    api.health().then((h) => setMock(h.mock)).catch(() => setError("Can't reach the backend. Is it running on :8000?"));
  }, []);

  const set = (k: keyof ProductBrief) => (e: { target: { value: string } }) => setBrief((b) => ({ ...b, [k]: e.target.value }));
  const ready = brief.problem.trim() && brief.audience.trim();

  const submit = async () => {
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    try {
      const clean = Object.fromEntries(Object.entries(brief).map(([k, v]) => [k, (v ?? "").trim() || null])) as ProductBrief;
      const { run_id } = await api.createRun({ brief: clean, candidate_count: count });
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError(`Couldn't start the run: ${(e as Error).message}`);
      setSubmitting(false);
    }
  };

  return (
    <div className="brief">
      <div className="brief__main">
        <header className="page-head">
          <h1>Brief the designer</h1>
          <p>Tell the designer what problem you're solving and who you're solving it for, as you would at a kickoff.
            Colors, fonts and layout are the designer's job, so you won't be asked about them.</p>
          {mock && <p className="note">Backend is in mock mode (UI_AGENT_MOCK=1): no API calls are made.</p>}
        </header>
        {error && <div className="callout callout--error">{error}</div>}

        <label className="field field--lead">
          <span>What problem are we solving?</span>
          <textarea rows={4} value={brief.problem} onChange={set("problem")} required
            placeholder="Freelancers lose receipts and dread tax season. Tracking expenses feels like a chore they put off until it's too late." />
        </label>
        <label className="field field--lead">
          <span>Who are we solving it for?</span>
          <textarea rows={3} value={brief.audience} onChange={set("audience")} required
            placeholder="Solo freelancers (designers, writers, developers) who do their own books, mostly on their phone between jobs. Skeptical of yet another finance app." />
        </label>

        <div className="field-row">
          <label className="field"><span>Product name <em className="optional">optional</em></span>
            <input value={brief.product_name ?? ""} onChange={set("product_name")} placeholder="Receiptly" /></label>
          <label className="field field--grow"><span>What should they do or come away with? <em className="optional">optional</em></span>
            <input value={brief.goal ?? ""} onChange={set("goal")} placeholder="Sign up for the free plan" /></label>
        </div>
        <label className="field"><span>Anything else the designer should know? <em className="optional">optional</em></span>
          <textarea rows={4} value={brief.context ?? ""} onChange={set("context")}
            placeholder="Constraints, an existing brand, competitors, what's been tried, real copy (headlines, pricing, quotes). Real text makes much better designs." /></label>
      </div>

      <aside className="brief__aside" aria-label="How it works and start">
        <div className="aside-card">
          <h2 className="h2">How it works</h2>
          <ol className="how">
            <li><strong>Kickoff.</strong> The designer reads your brief and may ask a question or two.</li>
            <li><strong>Sketches.</strong> {count} low-fi sketch{count > 1 ? "es" : ""}, each a different bet on how to solve the problem, with a proposed mood.</li>
            <li><strong>Pick one.</strong> Add notes if you like. It's designed in full, then reviewed and refined against a quality rubric.</li>
            <li><strong>Hand off.</strong> Approve it and download the HTML, tokens and spec for your coding agent.</li>
          </ol>
        </div>
        <div className="aside-card">
          <div className="generate-row">
            <div className="stepper" role="group" aria-label="Directions to sketch">
              <button aria-label="Fewer directions" onClick={() => setCount((c) => Math.max(MIN_COUNT, c - 1))} disabled={count <= MIN_COUNT}>−</button>
              <output aria-live="polite">{count}</output>
              <button aria-label="More directions" onClick={() => setCount((c) => Math.min(MAX_COUNT, c + 1))} disabled={count >= MAX_COUNT}>+</button>
            </div>
            <button className="btn btn--primary generate-row__btn" disabled={!ready || submitting} onClick={submit}>
              {submitting ? "Starting…" : !ready ? "Add the problem and users" : `Sketch ${count} direction${count > 1 ? "s" : ""}`}
            </button>
          </div>
          <p className="caption caption--tight">Directions to sketch. Sketches are quick; only the one you pick is designed in full.</p>
        </div>
      </aside>
    </div>
  );
}
