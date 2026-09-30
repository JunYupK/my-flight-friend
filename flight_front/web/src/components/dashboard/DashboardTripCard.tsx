import { Link } from "react-router-dom";
import { Check, Loader2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import CondPriceTag from "@/components/common/CondPriceTag";
import Money from "@/components/common/Money";
import ProviderBadge from "@/components/common/ProviderBadge";
import Sparkline from "@/components/common/Sparkline";
import { cityName } from "@/data/airports";
import { providerLabel, STATUS_REASON } from "@/lib/providers";
import { cn } from "@/lib/utils";
import type { LegSummary, TripSummary } from "@/types";
import { dday, formatDate, formatWon, nextAutoLabel, shortMd, timeAgo } from "@/utils";

const DAY_MS = 86_400_000;

function shortLabel(id: string): string {
  return id === "google_flights" ? "GF" : providerLabel(id);
}

function nightsOf(out: string, ret: string): number {
  const t = (d: string) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10));
  return Math.round((t(ret) - t(out)) / DAY_MS);
}

function LegLine({ label, leg }: { label: string; leg: LegSummary }) {
  const stops = leg.stops == null ? "" : leg.stops === 0 ? "직항" : `경유 ${leg.stops}`;
  const time = leg.dep_time && leg.arr_time ? `${leg.dep_time}→${leg.arr_time}` : "";
  return (
    <div className="flex min-w-0 items-baseline gap-2 text-xs">
      <span className="w-6 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate" title={leg.airline_name ?? leg.airline_iata ?? undefined}>
        {leg.airline_name ?? leg.airline_iata ?? "-"}
      </span>
      <span className="shrink-0 tabular-nums text-muted-foreground">{time}</span>
      <span className="shrink-0 text-muted-foreground">{stops}</span>
    </div>
  );
}

export default function DashboardTripCard({ trip }: { trip: TripSummary }) {
  const combo = trip.best_combo;
  const nights = nightsOf(trip.out_date, trip.ret_date);
  const outProv = combo?.out.best_provider ?? null;
  const inProv = combo?.in.best_provider ?? null;
  const badges = [outProv, inProv].filter((p, i, a): p is string => p != null && a.indexOf(p) === i);
  const mine = combo?.total ?? null;
  const cheaperThan =
    mine == null
      ? []
      : Object.entries(trip.provider_totals)
          .filter(([p, total]) => !badges.includes(p) && total > mine)
          .map(([p, total]) => ({ label: shortLabel(p), diff: total - mine }));
  const changePct = trip.change_vs_start_pct;
  const hasSeries = trip.series.filter((p) => p.combo != null).length >= 3;
  const target = trip.target_price;
  const cur = trip.current;
  const running = trip.open_run_id != null;

  // 확인한 적은 있지만 신선한 가격이 없음(모두 freshness window 밖) → best_combo null
  const checkedBefore = trip.series.length > 0 || Object.keys(trip.provider_status).length > 0;
  const lastChecked = trip.current_observed_at ?? trip.last_checked_at;
  let footer: string;
  if (lastChecked) footer = `${timeAgo(lastChecked)} 확인`;
  else footer = running ? "첫 확인 중…" : "아직 확인 전";
  if (trip.next_auto_at && trip.tracking && !trip.archived) footer += ` · 다음 자동 ${nextAutoLabel(trip.next_auto_at)}`;
  const failed = Object.entries(trip.provider_status)
    .filter(([, st]) => st !== "ok")
    .map(([p, st]) => `${shortLabel(p)} ${STATUS_REASON[st] ?? st}`);

  return (
    <Link
      to={`/trips/${trip.id}`}
      className="block rounded-2xl border bg-card p-4 text-card-foreground shadow-sm transition-colors hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-ring"
    >
      <div className="space-y-3">
        {/* 1. 머리 */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-semibold">
              {cityName(trip.destination) ?? trip.destination}{" "}
              <span className="text-muted-foreground">{trip.destination}</span>
            </div>
            <div className="text-xs text-muted-foreground">
              {formatDate(trip.out_date)} – {formatDate(trip.ret_date)} · {nights}박 {nights + 1}일
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {trip.tracking && !trip.archived && <Badge variant="secondary">추적 중</Badge>}
            <span className="text-sm font-medium tabular-nums">{dday(trip.days_to_departure)}</span>
          </div>
        </div>

        {/* 2. 가격 */}
        <div className="space-y-1">
          {mine != null ? (
            <>
              <div className="flex items-center gap-2">
                <Money value={mine} className="text-2xl font-bold" />
                <span className="flex items-center gap-1">
                  {badges.map((p) => (
                    <ProviderBadge key={p} provider={p} />
                  ))}
                </span>
              </div>
              {cheaperThan.map((c) => (
                <div key={c.label} className="text-xs text-muted-foreground">
                  {c.label}보다 {formatWon(c.diff)} 쌈
                </div>
              ))}
              {combo?.cond_total != null && (
                <div className="max-w-full sm:max-w-[320px]">
                  <CondPriceTag price={combo.cond_total} label={null} />
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-muted-foreground">
              {running ? "가격 확인 중" : checkedBefore ? "최신 가격 없음 · 다시 확인 필요" : "아직 확인 전"}
            </div>
          )}
        </div>

        {/* 3. 추이 */}
        <div className="flex h-16 items-center">
          {hasSeries ? (
            <Sparkline points={trip.series} low={trip.low} className="h-16 w-full" />
          ) : (
            <span className="text-xs text-muted-foreground">데이터 쌓는 중</span>
          )}
        </div>

        {/* 4. 통계 줄 */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {changePct != null && changePct !== 0 && (
            <span className={cn(changePct < 0 ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>
              시작 대비 {changePct < 0 ? "▼" : "▲"}
              {Math.abs(Math.round(changePct))}%
            </span>
          )}
          {trip.low != null && (
            <span className="tabular-nums">
              최저 {trip.low.toLocaleString("ko-KR")}
              {trip.low_day ? ` (${shortMd(trip.low_day)})` : ""}
            </span>
          )}
          {trip.is_low_now && <Badge>지금이 최저</Badge>}
        </div>

        {/* 5. 조합 요약 */}
        {combo && (
          <div className="space-y-0.5">
            <LegLine label="가는" leg={combo.out} />
            <LegLine label="오는" leg={combo.in} />
          </div>
        )}

        {/* 6. 목표가 */}
        {target != null && cur != null && (
          <div className="space-y-1">
            <Progress value={Math.min(100, Math.round((target / cur) * 100))} />
            <div className="text-xs text-muted-foreground">
              {cur <= target ? "목표 달성" : `목표까지 ${formatWon(cur - target)}`}
            </div>
          </div>
        )}

        {/* 7. 바닥줄 */}
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          {running ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="size-3 animate-spin" />
              확인 중…
            </span>
          ) : (
            <span className="min-w-0 truncate" title={footer}>
              {footer}
            </span>
          )}
          <span className="flex shrink-0 items-center gap-1.5">
            {Object.entries(trip.provider_status).map(([p, st]) => (
              <span
                key={p}
                title={`${providerLabel(p)} ${st === "ok" ? "정상" : (STATUS_REASON[st] ?? st)}`}
                className="inline-flex items-center gap-0.5"
              >
                <ProviderBadge provider={p} />
                {st === "ok" ? (
                  <Check className="size-3 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <X className="size-3 text-destructive" />
                )}
              </span>
            ))}
          </span>
        </div>
        {failed.length > 0 && (
          <div className="-mt-2 truncate text-right text-[11px] text-destructive" title={failed.join(" · ")}>
            {failed.join(" · ")}
          </div>
        )}
      </div>
    </Link>
  );
}
