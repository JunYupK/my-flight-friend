import type {
  AdminRun,
  DayPoint,
  ProviderDay,
  RunStatus,
  StartRunResult,
  TripCreateInput,
  TripPatchInput,
  TripSummary,
  TripView,
} from "./types";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

/** FastAPI 에러 detail(string | list)을 사람이 읽을 문자열로. */
function errorMessage(body: unknown, fallback: string): string {
  if (!isRecord(body)) return fallback;
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => {
      if (!isRecord(d)) return String(d);
      const loc = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
      const msg = typeof d.msg === "string" ? d.msg : "invalid";
      return loc ? `${loc}: ${msg}` : msg;
    });
    if (msgs.length > 0) return msgs.join("\n");
  }
  return fallback;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    throw new Error(errorMessage(body, `요청 실패 (${res.status})`));
  }
  const data: T = await res.json();
  return data;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listTrips(): Promise<TripSummary[]> {
  return request<TripSummary[]>("/api/trips");
}

export function createTrip(input: TripCreateInput): Promise<{ id: number; run_id: number }> {
  return request<{ id: number; run_id: number }>("/api/trips", jsonInit("POST", input));
}

export function getTrip(id: number): Promise<TripView> {
  return request<TripView>(`/api/trips/${id}`);
}

export function patchTrip(id: number, patch: TripPatchInput): Promise<TripView> {
  return request<TripView>(`/api/trips/${id}`, jsonInit("PATCH", patch));
}

/** 202 → started, 429 → cooldown. 그 외 오류는 throw. */
export async function startRun(id: number): Promise<StartRunResult> {
  const res = await fetch(`/api/trips/${id}/runs`, { method: "POST" });
  const body: unknown = await res.json().catch(() => null);
  if (res.status === 429) {
    const secs = isRecord(body) && typeof body.retry_after_seconds === "number" ? body.retry_after_seconds : 0;
    return { kind: "cooldown", cooldownSeconds: secs };
  }
  if (!res.ok || !isRecord(body) || typeof body.run_id !== "number") {
    throw new Error(errorMessage(body, `요청 실패 (${res.status})`));
  }
  return { kind: "started", runId: body.run_id };
}

export function getRun(id: number): Promise<RunStatus> {
  return request<RunStatus>(`/api/runs/${id}`);
}

export function getHistory(id: number): Promise<DayPoint[]> {
  return request<DayPoint[]>(`/api/trips/${id}/history`);
}

export function getAdminRuns(): Promise<AdminRun[]> {
  return request<AdminRun[]>("/api/admin/runs");
}

export function getAdminProviders(days: number): Promise<ProviderDay[]> {
  return request<ProviderDay[]>(`/api/admin/providers?days=${days}`);
}
