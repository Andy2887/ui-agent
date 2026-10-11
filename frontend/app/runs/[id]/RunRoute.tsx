"use client";
import { useParams } from "next/navigation";
import { RunView } from "@/components/RunView";

export function RunRoute() {
  const { id } = useParams<{ id: string }>();
  return <RunView runId={id} />;
}
