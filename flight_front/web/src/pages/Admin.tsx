import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminProviders, getAdminRuns } from "../api";
import { providerLabel, STATUS_REASON } from "@/lib/providers";
import type { AdminRun, ProviderDay, RunSnapshotStatus } from "../types";
import { timeAgo } from "../utils";

const DAY_OPTIONS = [7, 14, 30];

const RUN_STATUS: Record<string, string> = {
  queued: "대기",
  running: "진행 중",
  done: "완료",
  error: "오류",
};

function localTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "-";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function snapshotLabel(s: RunSnapshotStatus): string {
  const kind = s.kind === "roundtrip" ? "왕복" : s.direction === "in" ? "편도 귀국" : "편도 출국";
  return `${providerLabel(s.provider)} ${kind}`;
}

function SnapshotBadge({ s }: { s: RunSnapshotStatus }) {
  const ok = s.status === "ok";
  return (
    <span className="inline-block whitespace-nowrap rounded-full bg-apple-text/5 px-2 py-0.5 text-xs text-apple-text">
      {snapshotLabel(s)}{" "}
      {ok ? (
        <span className="text-green-600">✓</span>
      ) : (
        <>
          <span className="text-red-500">✕</span> {STATUS_REASON[s.status] ?? s.status}
        </>
      )}
    </span>
  );
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : "알 수 없는 오류";
}

function RunsSection({ refreshKey }: { refreshKey: number }) {
  const [runs, setRuns] = useState<AdminRun[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setError("");
    getAdminRuns()
      .then((r) => alive && setRuns(r))
      .catch((e: unknown) => alive && setError(errMsg(e)));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  return (
    <section>
      <h2 className="mb-2 text-base font-semibold text-apple-text">최근 실행</h2>
      {error && <p className="text-sm text-red-500">불러오지 못했습니다: {error}</p>}
      {!error && runs === null && <p className="text-sm text-apple-secondary">불러오는 중…</p>}
      {!error && runs !== null && runs.length === 0 && <p className="text-sm text-apple-secondary">실행 기록이 없습니다.</p>}
      {runs !== null && runs.length > 0 && (
        <div className="overflow-x-auto rounded-2xl bg-apple-surface">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-apple-secondary">
              <tr>
                <th className="px-3 py-2 font-medium whitespace-nowrap">요청 시각</th>
                <th className="px-3 py-2 font-medium">Trip</th>
                <th className="px-3 py-2 font-medium">트리거</th>
                <th className="px-3 py-2 font-medium">상태</th>
                <th className="px-3 py-2 font-medium">스냅샷</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-apple-text/5 align-top">
                  <td className="px-3 py-2 whitespace-nowrap">
                    {localTime(r.requested_at)}
                    <span className="block text-xs text-apple-secondary">{timeAgo(r.requested_at)}</span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <Link to={`/trips/${r.trip_id}`} className="underline">
                      {r.destination} #{r.trip_id}
                    </Link>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{r.trigger === "schedule" ? "자동" : r.trigger === "manual" ? "수동" : r.trigger}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{RUN_STATUS[r.status] ?? r.status}</td>
                  <td className="px-3 py-2">
                    <div className="flex min-w-[16rem] flex-wrap gap-1">
                      {r.snapshots.length === 0 ? (
                        <span className="text-xs text-apple-secondary">-</span>
                      ) : (
                        r.snapshots.map((s, i) => <SnapshotBadge key={i} s={s} />)
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ProvidersSection({ refreshKey }: { refreshKey: number }) {
  const [days, setDays] = useState(7);
  const [rows, setRows] = useState<ProviderDay[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setError("");
    setRows(null);
    getAdminProviders(days)
      .then((r) => alive && setRows(r))
      .catch((e: unknown) => alive && setError(errMsg(e)));
    return () => {
      alive = false;
    };
  }, [days, refreshKey]);

  // 서버는 일자 오름차순 → 화면은 제공자별로 묶고 최신 일자 먼저.
  const providers = rows ? Array.from(new Set(rows.map((r) => r.provider))) : [];

  return (
    <section>
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-apple-text">제공자 상태</h2>
        <div className="flex gap-1" role="group" aria-label="기간">
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={d === days}
              onClick={() => setDays(d)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                d === days ? "bg-apple-text text-apple-bg" : "bg-apple-text/5 text-apple-secondary"
              }`}
            >
              {d}일
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-sm text-red-500">불러오지 못했습니다: {error}</p>}
      {!error && rows === null && <p className="text-sm text-apple-secondary">불러오는 중…</p>}
      {!error && rows !== null && rows.length === 0 && <p className="text-sm text-apple-secondary">최근 {days}일간 기록이 없습니다.</p>}
      {rows !== null &&
        providers.map((p) => (
          <div key={p} className="mb-4 overflow-x-auto rounded-2xl bg-apple-surface">
            <table className="w-full text-left text-sm">
              <caption className="px-3 pt-3 pb-1 text-left text-sm font-medium text-apple-text">{providerLabel(p)}</caption>
              <thead className="text-xs text-apple-secondary">
                <tr>
                  <th className="px-3 py-2 font-medium">일자</th>
                  <th className="px-3 py-2 font-medium text-right">전체</th>
                  <th className="px-3 py-2 font-medium text-right">ok</th>
                  <th className="px-3 py-2 font-medium text-right">empty</th>
                  <th className="px-3 py-2 font-medium text-right">blocked</th>
                  <th className="px-3 py-2 font-medium text-right">error</th>
                  <th className="px-3 py-2 font-medium text-right">성공률</th>
                </tr>
              </thead>
              <tbody>
                {rows
                  .filter((r) => r.provider === p)
                  .sort((a, b) => (a.day < b.day ? 1 : -1))
                  .map((r) => (
                    <tr key={r.day} className="border-t border-apple-text/5">
                      <td className="px-3 py-2 whitespace-nowrap">{r.day.slice(5).replace("-", "/")}</td>
                      <td className="px-3 py-2 text-right">{r.total}</td>
                      <td className="px-3 py-2 text-right">{r.ok}</td>
                      <td className="px-3 py-2 text-right">{r.empty}</td>
                      <td className={`px-3 py-2 text-right ${r.blocked > 0 ? "text-red-500" : ""}`}>{r.blocked}</td>
                      <td className={`px-3 py-2 text-right ${r.error > 0 ? "text-red-500" : ""}`}>{r.error}</td>
                      <td className="px-3 py-2 text-right">{r.total > 0 ? `${Math.round((r.ok / r.total) * 100)}%` : "-"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ))}
    </section>
  );
}

export default function Admin() {
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  return (
    <div className="min-w-0 space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-apple-text">관리</h1>
        <button
          type="button"
          onClick={refresh}
          className="rounded-full bg-apple-text px-4 py-1.5 text-sm font-medium text-apple-bg"
        >
          새로고침
        </button>
      </div>
      <RunsSection refreshKey={refreshKey} />
      <ProvidersSection refreshKey={refreshKey} />
    </div>
  );
}
