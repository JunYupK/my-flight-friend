import type { ProviderStatus, RunStatus } from "../types";

export interface ProviderMeta {
  label: string;
  initial: string;
  colorVar: string;
}

export const PROVIDERS: Record<string, ProviderMeta> = {
  google_flights: { label: "Google Flights", initial: "G", colorVar: "--provider-google_flights" },
  naver: { label: "Naver", initial: "N", colorVar: "--provider-naver" },
};

/** 모르는 제공자는 회색 + 이름 첫 글자 대문자. */
export function providerMeta(id: string): ProviderMeta {
  return (
    PROVIDERS[id] ?? {
      label: id,
      initial: (id.charAt(0) || "?").toUpperCase(),
      colorVar: "--muted-foreground",
    }
  );
}

export function providerLabel(id: string): string {
  return providerMeta(id).label;
}

export const STATUS_REASON: Record<string, string> = {
  blocked: "차단 의심",
  empty: "결과 없음",
  error: "오류",
};

export interface ProviderMark {
  provider: string;
  state: "ok" | "fail" | "pending";
  reason: string | null;
}

const DEFAULT_PROVIDERS = ["google_flights"];

/** 마지막 확인 결과 기준 제공자 표시. */
export function marksFromStatuses(providers: ProviderStatus[]): ProviderMark[] {
  return providers.map((p) =>
    p.status === "ok"
      ? { provider: p.provider, state: "ok", reason: null }
      : { provider: p.provider, state: "fail", reason: STATUS_REASON[p.status] ?? p.status },
  );
}

/** 진행 중인 run의 snapshot 기준. snapshot이 아직 없는 제공자는 "진행 중". */
export function marksFromRun(run: RunStatus | null, known: ProviderStatus[]): ProviderMark[] {
  const ids: string[] = known.map((p) => p.provider);
  for (const s of run?.snapshots ?? []) if (!ids.includes(s.provider)) ids.push(s.provider);
  if (ids.length === 0) ids.push(...DEFAULT_PROVIDERS);
  return ids.map((id) => {
    const snaps = (run?.snapshots ?? []).filter((s) => s.provider === id);
    if (snaps.length === 0) return { provider: id, state: "pending", reason: null };
    if (snaps.some((s) => s.status === "ok")) return { provider: id, state: "ok", reason: null };
    const bad = snaps.find((s) => s.status !== "ok");
    const st = bad ? bad.status : "error";
    return { provider: id, state: "fail", reason: STATUS_REASON[st] ?? st };
  });
}
