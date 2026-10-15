import { Suspense } from "react";
import { RunRoute } from "./RunRoute";

export default function RunPage() {
  return (
    <Suspense fallback={<div className="page"><p className="muted" role="status"><span className="spinner" /> Loading run…</p></div>}>
      <RunRoute />
    </Suspense>
  );
}
