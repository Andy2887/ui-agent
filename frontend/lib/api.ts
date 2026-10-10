import type { Preferences, Presets } from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { detail = JSON.stringify((await res.json()).detail ?? detail); } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API}/health`).then(json<{ ok: boolean; mock: boolean; models: Record<string, string> }>),
  presets: () => fetch(`${API}/presets`).then(json<Presets>),
  lastPreferences: () =>
    fetch(`${API}/memory/last-preferences`).then(json<{ preferences: Preferences | null; candidate_count: number | null }>),
  createRun: (body: { prompt: string; preferences: Preferences; candidate_count: number }) =>
    fetch(`${API}/runs`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then(json<{ run_id: string }>),
  listRuns: () => fetch(`${API}/runs`).then(json<{ run_id: string; prompt: string; status: string }[]>),
  resume: (runId: string, body: Record<string, unknown>) =>
    fetch(`${API}/runs/${runId}/resume`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then(json<{ ok: boolean }>),
  memory: () => fetch(`${API}/memory`).then(json<any>),
  resetMemory: (what: string) => fetch(`${API}/memory?what=${what}`, { method: "DELETE" }).then(json<{ ok: boolean }>),
};

export const artifactUrl = (runId: string, path: string) => `${API}/runs/${runId}/artifacts/${path}`;
export const downloadUrl = (runId: string, kind: string) => `${API}/runs/${runId}/download/${kind}`;
export const eventsUrl = (runId: string, since = 0) => `${API}/runs/${runId}/events?since=${since}`;
