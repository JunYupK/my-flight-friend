import type { ConfigData, RunStatus, DestinationGroup } from "./types";

export async function fetchConfig(): Promise<ConfigData> {
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export async function saveConfig(data: ConfigData): Promise<void> {
  const res = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to save config");
}

export async function startRun(): Promise<void> {
  const res = await fetch("/api/run", { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to start run");
  }
}

export async function fetchRunStatus(): Promise<RunStatus> {
  const res = await fetch("/api/run/status");
  if (!res.ok) throw new Error("Failed to fetch run status");
  return res.json();
}

export async function fetchResults(): Promise<DestinationGroup[]> {
  const res = await fetch("/api/results");
  if (!res.ok) throw new Error("Failed to fetch results");
  return res.json();
}
