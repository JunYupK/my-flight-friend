import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, History, RefreshCw } from "lucide-react";
import { getAdminProviders, getAdminRuns } from "@/api";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import ProviderBadge from "@/components/common/ProviderBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { providerLabel, STATUS_REASON } from "@/lib/providers";
import { cn } from "@/lib/utils";
import type { AdminRun, AdminRunSnapshot, ProviderDay } from "@/types";
import { timeAgo } from "@/utils";

const DAY_OPTIONS = [7, 14, 30];

const RUN_STATUS: Record<string, string> = {
  queued: "대기",
  running: "진행 중",
  done: "완료",
  error: "오류",
};

const TRIGGER: Record<string, string> = { schedule: "자동", manual: "수동" };

const CHIP_TONE: Record<string, string> = {
  ok: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  blocked: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  empty: "bg-muted text-muted-foreground",
  error: "bg-destructive/10 text-destructive",
};

const card = "rounded-2xl border bg-card text-card-foreground shadow-sm";

function localTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "-";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function kindLabel(s: AdminRunSnapshot): string {
  return s.kind === "roundtrip" ? "왕복" : s.direction === "in" ? "귀국" : "출국";
}

function statusText(status: string): string {
  return status === "ok" ? "✓" : (STATUS_REASON[status] ?? status);
}

function pct(ok: number, total: number): number | null {
  return total > 0 ? Math.round((ok / total) * 100) : null;
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : "알 수 없는 오류";
}

/** 스냅샷 상태 칩. 실패면 툴팁(+ 네이티브 title)에 error. */
function SnapshotChip({ s }: { s: AdminRunSnapshot }) {
  const full = `${providerLabel(s.provider)} ${kindLabel(s)} · ${s.status === "ok" ? "정상" : statusText(s.status)}${
    s.error ? ` — ${s.error}` : ""
  }`;
  const chip = (
    <span
      title={full}
      tabIndex={s.error ? 0 : undefined}
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs",
        CHIP_TONE[s.status] ?? CHIP_TONE.empty,
      )}
    >
      <ProviderBadge provider={s.provider} />
      <span className="text-foreground/70">{kindLabel(s)}</span>
      <span className="font-medium">{statusText(s.status)}</span>
    </span>
  );
  if (!s.error) return chip;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{chip}</TooltipTrigger>
      <TooltipContent>{s.error}</TooltipContent>
    </Tooltip>
  );
}

function Chips({ snapshots }: { snapshots: AdminRunSnapshot[] }) {
  if (snapshots.length === 0) return <span className="text-xs text-muted-foreground">-</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {snapshots.map((s, i) => (
        <SnapshotChip key={i} s={s} />
      ))}
    </div>
  );
}

function TripLink({ r }: { r: AdminRun }) {
  return (
    <Link to={`/trips/${r.trip_id}`} className="underline-offset-4 hover:underline">
      {r.destination} #{r.trip_id}
    </Link>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-base font-semibold">{children}</h2>;
}

function RunsSection({ refreshKey, onRetry }: { refreshKey: number; onRetry: () => void }) {
  const [runs, setRuns] = useState<AdminRun[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setError("");
    setRuns(null);
    getAdminRuns()
      .then((r) => alive && setRuns(r))
      .catch((e: unknown) => alive && setError(errMsg(e)));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  let body: ReactNode;
  if (error) body = <ErrorState message={`불러오지 못했습니다: ${error}`} onRetry={onRetry} />;
  else if (runs === null)
    body = (
      <div className="space-y-2 p-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  else if (runs.length === 0) body = <EmptyState icon={History} title="실행 기록이 없습니다" />;
  else
    body = (
      <>
        {/* ≥640px: 표 */}
        <div className="hidden overflow-x-auto sm:block">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium whitespace-nowrap">요청 시각</th>
                <th className="px-4 py-2 font-medium">Trip</th>
                <th className="px-4 py-2 font-medium">트리거</th>
                <th className="px-4 py-2 font-medium">상태</th>
                <th className="px-4 py-2 font-medium">스냅샷</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t align-top">
                  <td className="px-4 py-2 whitespace-nowrap tabular-nums">
                    {localTime(r.requested_at)}
                    <span className="block text-xs text-muted-foreground">{timeAgo(r.requested_at)}</span>
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    <TripLink r={r} />
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">{TRIGGER[r.trigger] ?? r.trigger}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{RUN_STATUS[r.status] ?? r.status}</td>
                  <td className="px-4 py-2">
                    <Chips snapshots={r.snapshots} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* <640px: 카드 목록. 툴팁은 탭으로 안 열리므로 오류 문구를 그대로 보여 준다. */}
        <ul className="divide-y sm:hidden">
          {runs.map((r) => (
            <li key={r.id} className="space-y-2 px-4 py-3">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="min-w-0 truncate font-medium">
                  <TripLink r={r} />
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {TRIGGER[r.trigger] ?? r.trigger} · {RUN_STATUS[r.status] ?? r.status}
                </span>
              </div>
              <div className="text-xs text-muted-foreground tabular-nums">
                {localTime(r.requested_at)} · {timeAgo(r.requested_at)}
              </div>
              <Chips snapshots={r.snapshots} />
              {r.snapshots
                .filter((s) => s.error)
                .map((s, i) => (
                  <p key={i} className="break-all text-xs text-destructive">
                    {providerLabel(s.provider)} {kindLabel(s)}: {s.error}
                  </p>
                ))}
            </li>
          ))}
        </ul>
      </>
    );

  return (
    <section className="space-y-3">
      <SectionTitle>최근 실행</SectionTitle>
      <div className={card}>{body}</div>
    </section>
  );
}

function RateBar({ value }: { value: number | null }) {
  return (
    <div className="h-1.5 w-full min-w-10 overflow-hidden rounded-full bg-muted" aria-hidden>
      <div
        className={cn("h-full rounded-full", value != null && value < 50 ? "bg-destructive" : "bg-primary")}
        style={{ width: `${value ?? 0}%` }}
      />
    </div>
  );
}

function ProviderCard({ provider, rows }: { provider: string; rows: ProviderDay[] }) {
  const sorted = [...rows].sort((a, b) => (a.day < b.day ? 1 : -1));
  const total = rows.reduce((n, r) => n + r.total, 0);
  const ok = rows.reduce((n, r) => n + r.ok, 0);
  const rate = pct(ok, total);
  const warn = (n: number) => (n > 0 ? "text-destructive" : "");
  return (
    <div className={card}>
      <div className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
        <span className="inline-flex items-center gap-2 font-medium">
          <ProviderBadge provider={provider} size="md" />
          {providerLabel(provider)}
        </span>
        <span className="text-sm text-muted-foreground tabular-nums">
          성공률 {rate != null ? `${rate}%` : "-"} · {ok}/{total}
        </span>
      </div>
      {/* ≥640px: 표 */}
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full text-left text-sm tabular-nums">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">일자</th>
              <th className="px-4 py-2 text-right font-medium">전체</th>
              <th className="px-4 py-2 text-right font-medium">✓</th>
              <th className="px-4 py-2 text-right font-medium">결과 없음</th>
              <th className="px-4 py-2 text-right font-medium">차단 의심</th>
              <th className="px-4 py-2 text-right font-medium">오류</th>
              <th className="w-40 px-4 py-2 font-medium">성공률</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const p = pct(r.ok, r.total);
              return (
                <tr key={r.day} className="border-t">
                  <td className="px-4 py-2 whitespace-nowrap">{r.day.slice(5).replace("-", "/")}</td>
                  <td className="px-4 py-2 text-right">{r.total}</td>
                  <td className="px-4 py-2 text-right">{r.ok}</td>
                  <td className="px-4 py-2 text-right">{r.empty}</td>
                  <td className={cn("px-4 py-2 text-right", warn(r.blocked))}>{r.blocked}</td>
                  <td className={cn("px-4 py-2 text-right", warn(r.error))}>{r.error}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <RateBar value={p} />
                      <span className="w-10 shrink-0 text-right">{p != null ? `${p}%` : "-"}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* <640px: 카드 목록 */}
      <ul className="divide-y border-t sm:hidden">
        {sorted.map((r) => {
          const p = pct(r.ok, r.total);
          return (
            <li key={r.day} className="space-y-1 px-4 py-2 text-sm tabular-nums">
              <div className="flex items-center gap-3">
                <span className="w-12 shrink-0">{r.day.slice(5).replace("-", "/")}</span>
                <RateBar value={p} />
                <span className="w-10 shrink-0 text-right">{p != null ? `${p}%` : "-"}</span>
              </div>
              <div className="text-xs text-muted-foreground">
                전체 {r.total} · ✓ {r.ok} · 결과 없음 {r.empty} ·{" "}
                <span className={warn(r.blocked)}>차단 {r.blocked}</span> ·{" "}
                <span className={warn(r.error)}>오류 {r.error}</span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ProvidersSection({ refreshKey, onRetry }: { refreshKey: number; onRetry: () => void }) {
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

  const providers = rows ? Array.from(new Set(rows.map((r) => r.provider))) : [];

  let body: ReactNode;
  if (error)
    body = (
      <div className={card}>
        <ErrorState message={`불러오지 못했습니다: ${error}`} onRetry={onRetry} />
      </div>
    );
  else if (rows === null)
    body = (
      <div className="space-y-3">
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-40 w-full rounded-2xl" />
        ))}
      </div>
    );
  else if (rows.length === 0)
    body = (
      <div className={card}>
        <EmptyState icon={Activity} title={`최근 ${days}일간 기록이 없습니다`} />
      </div>
    );
  else
    body = (
      <div className="space-y-3">
        {providers.map((p) => (
          <ProviderCard key={p} provider={p} rows={rows.filter((r) => r.provider === p)} />
        ))}
      </div>
    );

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <SectionTitle>제공자별 일자 성공률</SectionTitle>
        <div className="flex shrink-0 gap-1" role="group" aria-label="기간">
          {DAY_OPTIONS.map((d) => (
            <Button
              key={d}
              size="sm"
              variant={d === days ? "secondary" : "ghost"}
              aria-pressed={d === days}
              onClick={() => setDays(d)}
              className="h-7 rounded-full px-3 text-xs"
            >
              {d}일
            </Button>
          ))}
        </div>
      </div>
      {body}
    </section>
  );
}

export default function Admin() {
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  return (
    <div className="min-w-0 space-y-8">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">관리</h1>
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw />
          새로고침
        </Button>
      </div>
      <RunsSection refreshKey={refreshKey} onRetry={refresh} />
      <ProvidersSection refreshKey={refreshKey} onRetry={refresh} />
    </div>
  );
}
