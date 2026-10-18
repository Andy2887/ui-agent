"use client";
// Screen 1 — Brief (§5): the PM describes the problem and what users do. The pages, the users and the look are the designer's to work out.
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ProductBrief } from "@/lib/types";
import { Icon } from "./Icon";

const MAX_FLOWS = 5;
const FLOW_PLACEHOLDERS = [
  "A freelancer hears about us from a friend, checks how receipt capture works and what it costs, then starts a free trial.",
  "A returning user signs in at tax time and exports a year of receipts for their accountant.",
];

export function BriefScreen() {
  const router = useRouter();
  const [brief, setBrief] = useState<Omit<ProductBrief, "flows">>({ problem: "", product_name: "", context: "" });
  const [flows, setFlows] = useState<string[]>([""]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mock, setMock] = useState(false);

  useEffect(() => {
    api.health().then((h) => setMock(h.mock)).catch(() => setError("Can't reach the backend. Is it running on :8000?"));
  }, []);

  const set = (k: keyof typeof brief) => (e: { target: { value: string } }) => setBrief((b) => ({ ...b, [k]: e.target.value }));
  const setFlow = (i: number, v: string) => setFlows((f) => f.map((x, j) => (j === i ? v : x)));
  const missing = !brief.problem.trim() ? "Add the problem first" : !flows[0].trim() ? "Add a user flow first" : null;

  const submit = async () => {
    if (missing) return;
    setSubmitting(true);
    setError(null);
    try {
      const clean = Object.fromEntries(Object.entries(brief).map(([k, v]) => [k, (v ?? "").trim() || null]));
      const { run_id } = await api.createRun({ brief: { ...clean, flows: flows.map((f) => f.trim()).filter(Boolean) } as ProductBrief });
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
          <p>Tell the designer what problem you're solving and what your users do, as you would at a kickoff. The designer works out
            who it&apos;s for, which pages that takes, and how they look, so you won't be asked about colors, fonts or layout.</p>
          {mock && <p className="note"><span className="tag tag--dot">Mock mode</span> UI_AGENT_MOCK=1, so no API calls are made.</p>}
        </header>
        {error && <div className="callout callout--error" role="alert"><Icon name="alert" /><div>{error}</div></div>}

        <div className="card brief__form">
          <label className="field field--lead">
            <span>What problem are we solving?</span>
            <textarea rows={4} value={brief.problem} onChange={set("problem")} required
              placeholder="Freelancers lose receipts and dread tax season. Tracking expenses feels like a chore they put off until it's too late." />
          </label>

          <fieldset className="flows">
            <legend>User flows</legend>
            <p className="field__hint">Describe what a user does, start to finish, in your own words. The designer turns each flow into the pages it needs and links them up. The first flow is required.</p>
            {flows.map((f, i) => (
              <div key={i} className="flow-field">
                <label className="field">
                  <span>Flow {i + 1} {i > 0 && <em className="optional">optional</em>}</span>
                  <textarea rows={3} value={f} onChange={(e) => setFlow(i, e.target.value)} required={i === 0}
                    placeholder={FLOW_PLACEHOLDERS[i] ?? "Another thing a user does, start to finish."} />
                </label>
                {i > 0 && <button className="btn btn--sm flow-field__remove" aria-label={`Remove flow ${i + 1}`}
                  onClick={() => setFlows((x) => x.filter((_, j) => j !== i))}><Icon name="x" size={14} />Remove</button>}
              </div>
            ))}
            {flows.length < MAX_FLOWS && <button className="btn btn--sm flows__add" onClick={() => setFlows((x) => [...x, ""])}><Icon name="plus" size={14} />Add another flow</button>}
          </fieldset>

          <div className="field-row">
            <label className="field"><span>Product name <em className="optional">optional</em></span>
              <input value={brief.product_name ?? ""} onChange={set("product_name")} placeholder="Receiptly" /></label>
          </div>
          <label className="field"><span>Anything else the designer should know? <em className="optional">optional</em></span>
            <textarea rows={4} value={brief.context ?? ""} onChange={set("context")}
              placeholder="Constraints, an existing brand, competitors, what's been tried, real copy (headlines, pricing, quotes). Real text makes much better designs." /></label>
        </div>
      </div>

      <aside className="brief__aside" aria-label="How it works and start">
        <div className="aside-card">
          <h2 className="h2">How it works</h2>
          <ol className="how">
            <li><strong>Kickoff.</strong> The designer reads your brief, works out the pages your flows need, and may ask a question or two.</li>
            <li><strong>Sketches.</strong> One direction for the whole site: a design system, and a low-fi sketch of every page.</li>
            <li><strong>Approve.</strong> Add notes, or ask for changes. Then every page is designed in the same design system, reviewed and refined against a quality rubric.</li>
            <li><strong>Hand off.</strong> Click through the pages, approve them, and download the HTML, tokens, flows and spec for your coding agent.</li>
          </ol>
        </div>
        <div className="aside-card">
          <button className="btn btn--primary btn--block generate-row__btn" disabled={!!missing || submitting} onClick={submit}>
            {submitting ? <><span className="spinner" />Starting…</> : missing ?? <>Start the kickoff<Icon name="arrowRight" /></>}
          </button>
          <p className="caption caption--tight">Up to 6 pages are designed per run. Sketches come first, so nothing is designed in full until you approve.</p>
        </div>
      </aside>
    </div>
  );
}
