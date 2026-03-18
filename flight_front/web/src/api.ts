import type { ConfigData, RunStatus, DestinationGroup, Airport, PriceHistoryResponse } from "./types";

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

export async function fetchAirports(): Promise<Airport[]> {
  const res = await fetch("/api/airports");
  if (!res.ok) throw new Error("Failed to fetch airports");
  return res.json();
}

export async function upsertAirport(airport: Airport): Promise<void> {
  const res = await fetch("/api/airports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(airport),
  });
  if (!res.ok) throw new Error("Failed to save airport");
}

export async function deleteAirport(code: string): Promise<void> {
  const res = await fetch(`/api/airports/${code}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete airport");
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

export async function fetchResults(params?: { hours?: number; month?: string }): Promise<DestinationGroup[]> {
  const qs = new URLSearchParams();
  if (params?.hours != null) qs.set("hours", String(params.hours));
  if (params?.month) qs.set("month", params.month);
  const query = qs.toString();
  const url = query ? `/api/results?${query}` : "/api/results";
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Failed to fetch results");
  }
  return res.json();
}

export async function fetchPriceHistory(params: {
  destination: string;
  mode?: "calendar" | "timeline";
  month?: string;
  stay_nights?: number;
  departure_date?: string;
  return_date?: string;
}): Promise<PriceHistoryResponse> {
  const qs = new URLSearchParams();
  qs.set("destination", params.destination);
  if (params.mode) qs.set("mode", params.mode);
  if (params.month) qs.set("month", params.month);
  if (params.stay_nights != null) qs.set("stay_nights", String(params.stay_nights));
  if (params.departure_date) qs.set("departure_date", params.departure_date);
  if (params.return_date) qs.set("return_date", params.return_date);
  const res = await fetch(`/api/price-history?${qs}`);
  if (!res.ok) throw new Error("Failed to fetch price history");
  return res.json();
}
