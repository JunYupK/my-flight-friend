import { useEffect, useState } from "react";
import { ArrowDown, ExternalLink, SearchX } from "lucide-react";
import { getHistory } from "@/api";
import CondPriceTag from "@/components/common/CondPriceTag";
import EmptyState from "@/components/common/EmptyState";
import Money from "@/components/common/Money";
import ProviderBadge from "@/components/common/ProviderBadge";
import Sparkline from "@/components/common/Sparkline";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DayPoint, MergedLegView, Stats, TripView } from "@/types";
import { shortMd } from "@/utils";

function condPrice(leg: MergedLegView): number {
  return Math.min(leg.best_cond?.price ?? Infinity, leg.best_price ?? Infinity);
}

function LegRow({
  label,
  leg,
  onJump,
}: {
  label: string;
  leg: MergedLegView;
  onJump: () => void;
}) {
  const overnight = leg.dep_time != null && leg.arr_time != null && leg.arr_time < leg.dep_time;
  const stops = leg.stops === 0 ? "직항" : leg.stops != null ? `경유 ${leg.stops}회` : null;
  const best = leg.prices.find((p) => p.provider === leg.best_provider && !p.stale && p.booking_url);
  return (
    <div className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0 flex-1">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="font-semibold tabular-nums">
          {leg.dep_time ?? "--:--"} → {leg.arr_time ?? "--:--"}
          {overnight && <span className="ml-1 text-xs font-medium text-amber-600 dark:text-amber-400">+1</span>}
        </div>
        <div className="flex min-w-0 items-center gap-x-2 text-xs text-muted-foreground">
          <span className="truncate">{leg.airline_name ?? leg.airline_iata ?? "항공사 미상"}</span>
          {stops && <span className="shrink-0">{stops}</span>}
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <span className="inline-flex items-center gap-1.5">
          {leg.best_provider && <ProviderBadge provider={leg.best_provider} />}
          {leg.best_price != null && <Money value={leg.best_price} className="text-sm font-medium" />}
        </span>
        <span className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" aria-label="목록에서 보기" onClick={onJump}>
            <ArrowDown />
          </Button>
          {best?.booking_url && (
            <Button asChild variant="outline" size="sm">
              <a href={best.booking_url} target="_blank" rel="noopener noreferrer">
                {leg.best_provider === "naver" ? "판매사 선택" : "예약"}
                <ExternalLink />
              </a>
            </Button>
          )}
        </span>
      </div>
    </div>
  );
}

function TrackingSummary({ stats, points }: { stats: Stats; points: DayPoint[] }) {
  const comparable = stats.current != null && stats.comparable && stats.start != null && stats.low != null;
  const pct =
    comparable && (stats.start as number) > 0
      ? (((stats.current as number) - (stats.start as number)) / (stats.start as number)) * 100
      : null;
  return (
    <div className="space-y-3">
      <div className="text-xs font-medium text-muted-foreground">추적 요약</div>
      {comparable ? (
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">
              시작 대비{stats.start_day ? ` (${shortMd(stats.start_day)})` : ""}
            </dt>
            <dd
              className={cn(
                "font-semibold tabular-nums",
                pct != null && pct < 0 && "text-emerald-600 dark:text-emerald-400",
                pct != null && pct > 0 && "text-destructive",
              )}
            >
              {pct == null ? "-" : `${pct < 0 ? "▼" : pct > 0 ? "▲" : ""}${Math.abs(pct).toFixed(1)}%`}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">
              최저{stats.low_day ? ` (${shortMd(stats.low_day)})` : ""}
            </dt>
            <dd className="font-semibold">
              <Money value={stats.low as number} />
            </dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">추적 {stats.days}일째 · 비교 이력 수집 중</p>
      )}
      {points.filter((p) => p.combo != null).length >= 2 && (
        <Sparkline points={points} low={stats.low} className="h-16 w-full" />
      )}
    </div>
  );
}

interface Props {
  view: TripView;
  onSelect: (outKey: string, inKey: string) => void;
  onJump: (direction: "out" | "in", key: string) => void;
}

export default function BestComboHero({ view, onSelect, onJump }: Props) {
  const tripId = view.trip.id;
  const refreshKey = `${view.stats.current ?? ""}|${view.run ? `${view.run.id}:${view.run.status}` : ""}`;
  const [points, setPoints] = useState<DayPoint[]>([]);

  useEffect(() => {
    let cancelled = false;
    getHistory(tripId)
      .then((d) => {
        if (!cancelled) setPoints(d);
      })
      .catch(() => {
        if (!cancelled) setPoints([]);
      });
    return () => {
      cancelled = true;
    };
  }, [tripId, refreshKey]);

  let best = view.candidates[0];
  for (const c of view.candidates) if (c.price < best.price) best = c;
  const out = best ? view.legs.out.find((l) => l.flight_key === best.out_flight_key) : undefined;
  const inn = best ? view.legs.in.find((l) => l.flight_key === best.in_flight_key) : undefined;

  if (!best || !out || !inn) {
    return (
      <section className="rounded-2xl border bg-card text-card-foreground shadow-sm">
        <EmptyState icon={SearchX} title="조건에 맞는 조합이 없어요" />
      </section>
    );
  }

  const hasCond = out.best_cond != null || inn.best_cond != null;
  const condTotal = hasCond ? condPrice(out) + condPrice(inn) : null;
  const condLabel = out.best_cond && inn.best_cond ? null : (out.best_cond ?? inn.best_cond)?.label ?? null;

  return (
    <section className="grid gap-x-8 gap-y-5 rounded-2xl border bg-card p-4 text-card-foreground shadow-sm sm:p-5 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-medium text-muted-foreground">지금 최선</div>
            <Money value={best.price} className="block text-3xl font-bold tracking-tight" />
            {condTotal != null && (
              <div className="mt-1 max-w-full">
                <CondPriceTag price={condTotal} label={condLabel} />
              </div>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={() => onSelect(best.out_flight_key, best.in_flight_key)}>
            이 조합 선택
          </Button>
        </div>
        <div className="mt-4 divide-y border-t pt-3">
          <LegRow label="가는 편" leg={out} onJump={() => onJump("out", out.flight_key)} />
          <LegRow label="오는 편" leg={inn} onJump={() => onJump("in", inn.flight_key)} />
        </div>
      </div>
      <div className="min-w-0 border-t pt-4 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
        <TrackingSummary stats={view.stats} points={points} />
      </div>
    </section>
  );
}
