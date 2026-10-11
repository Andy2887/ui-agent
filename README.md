# UI Agent — prototype

You brief it like a PM briefs a UI/UX designer: the problem and the users, never the colors, fonts or layout. The designer agent may ask a few kickoff questions, then sketches N low-fidelity directions (default 3), each a different bet on solving the problem with a proposed visual mood. You pick one; it is designed in full, then a reviewer/executor loop refines it against a rubric, and you get a handoff package (`index.html`, `tokens.json`, `HANDOFF.md`, screenshots, PDF) for a coding agent. See `plan.md` for the full design.

## Run it

Requirements: Python ≥ 3.11, Node ≥ 20.

```bash
# Backend (FastAPI + LangGraph + Playwright)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m playwright install chromium

export ANTHROPIC_API_KEY=...            # real mode (Claude Sonnet 5.5 for every role, see config.yaml)
# or: export UI_AGENT_MOCK=1            # offline mode: no API calls, deterministic stand-ins
.venv/bin/uvicorn ui_agent.api.app:app --port 8000

# Frontend (Next.js)
cd frontend && npm install && npm run dev   # http://localhost:3000
```

`NEXT_PUBLIC_API_URL` overrides the backend URL (default `http://localhost:8000`).

**Mock mode** (`UI_AGENT_MOCK=1`) runs the real pipeline end to end: real rendering, real Layer-A audits, real gate logic, and real `str_replace` edits through the sandboxed editor. Only the LLM calls are replaced. The mock designer asks one kickoff question when the brief has no goal. Generated pages contain seeded defects (missing focus states, small tap targets, 11px text, hard-coded values, a weak CTA), so you can watch the loop find and fix them.

## Dev tools and tests

```bash
.venv/bin/python scripts/audit.py page.html                       # Layer-A report for one file
.venv/bin/python scripts/refine.py page.html --problem "…" --audience "…"   # refine loop only
.venv/bin/python -m pytest -q                                     # 26 tests: presets CI, M0 checks, units, full mock pipeline
```

## Layout

```
presets/            the designer's library: styles, layouts, colors (OKLCH ranges + AA-validated examples), typography, options
config.yaml         role → model/effort, thresholds, viewports, budget
rubric/rubric.yaml  Layer A gates + Layer B anchored criteria and weights
prompts/            intake, planner, sketcher (+ sketch_contract, sketch_kit.css), generator, html_contract, style_lock, reviewer, executor, handoff
src/ui_agent/
  graph.py          top-level graph (plan §3.1)        refine_graph.py  refine-loop subgraph
  llm.py            the one Claude wrapper             mock.py          offline stand-ins
  nodes/            intake (+ kickoff), planner, sketch, gallery, generator (design), style_lock, reviewer, gate, executor, final_approval, handoff
  tools/            browser.py (Playwright, tiles, DOM facts), checks/ (A1–A8), text_editor.py (sandbox)
  memory/store.py   taste / lessons / runs on the LangGraph Store (SQLite)
  api/              FastAPI app + run manager (SSE with replay)
frontend/           Brief, Kickoff, Sketching, Pick a sketch, Designing & refining, Final review, Download, Runs, Memory
runs/<id>/          sketches/, refine/ (vN.html, shots, review JSON), output/ (handoff), handoff.zip, events.jsonl
```

## What the prototype covers, and what it simplifies

Implemented as planned:
- The whole graph: `Send` fan-out with a parallelism cap, all three interrupts (kickoff questions, sketch pick, final approval), SQLite checkpointer (runs resume after a page reload), and SQLite Store memory.
- Code-enforced direction diversity (concept, layout, type, palette, density, style, section order, theme) and contrast repair. The gate does pass, revert-to-best, plateau, max iterations and budget, and always outputs the best version.
- The Claude call shape from §10: structured outputs, adaptive thinking with per-role effort, streaming, a cached system prefix, `fallbacks: "default"`, refusal and max-token handling, and per-node usage and cost tracking.
- The Brief screen (problem, users, optional name, goal and context), kickoff questions with one-click suggested answers, and sketch cards that show each direction's concept, trade-off and mood (palette, fonts, theme).

Simplified or not yet built:
- **A6** checks console/page errors plus document basics (doctype, `lang`, viewport). `html-validate` is not wired in yet.
- **Not built:** the evals (§13), tracing (LangSmith/Langfuse), the project brand-kit UI (the Store namespace exists), Postgres, and the MCP server.
- **Refine subgraph:** a compiled subgraph used directly as a node would write its whole output back through the parent's reducers and double-count `history` and `usage`. So it runs inside a wrapper node that returns only its changes.
- **Real mode is untested against the live API** in this environment (no key was available). Request payloads for every role were checked against a local stub server. Expect prompt tuning once real runs happen.
