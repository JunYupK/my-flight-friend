import { useState } from "react";
import CondPriceTag from "@/components/common/CondPriceTag";
import Money from "@/components/common/Money";
import ProviderBadge from "@/components/common/ProviderBadge";
import ProviderPriceRow from "@/components/common/ProviderPriceRow";
import StaleBadge from "@/components/common/StaleBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { providerLabel } from "@/lib/providers";
import { cn } from "@/lib/utils";
import type { MergedLegView } from "@/types";

interface Props {
  leg: MergedLegView;
  direction: "out" | "in";
  selected: boolean;
  highlighted: boolean;
  onSelect: () => void;
}

function legDuration(min: number | null): string {
  if (min == null) return "";
  return `${Math.floor(min / 60)}시간 ${min % 60}분`;
}

export function legDomId(direction: "out" | "in", key: string): string {
  return `leg-${direction}-${key}`;
}

const linkCls = "shrink-0 text-primary hover:underline";

export default function LegCard({ leg, direction, selected, highlighted, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const selectable = leg.best_price != null;
  const overnight = leg.dep_time != null && leg.arr_time != null && leg.arr_time < leg.dep_time;
  const airline = leg.airline_name ?? leg.airline_iata ?? "항공사 미상";

  const summary = (
    <>
      <div className="min-w-0">
        <div className="text-lg font-semibold tabular-nums">
          {leg.dep_time ?? "--:--"} → {leg.arr_time ?? "--:--"}
          {overnight && <span className="ml-1 text-xs font-medium text-amber-600 dark:text-amber-400">+1</span>}
        </div>
        <div className="flex min-w-0 items-center gap-x-2 text-sm text-muted-foreground">
          <span className="truncate" title={airline}>
            {airline}
          </span>
          {leg.stops === 0 ? (
            <span className="shrink-0">직항</span>
          ) : leg.stops != null ? (
            <span className="shrink-0 text-amber-600 dark:text-amber-400">경유 {leg.stops}회</span>
          ) : null}
          {leg.duration_min != null && <span className="shrink-0">{legDuration(leg.duration_min)}</span>}
          {!leg.in_condition && <span className="shrink-0 text-amber-600 dark:text-amber-400">조건 밖</span>}
        </div>
      </div>
      <div className="flex min-w-0 max-w-full flex-col gap-1 sm:max-w-[60%] sm:items-end">
        {leg.prices.length > 0 ? (
          <ProviderPriceRow prices={leg.prices} bestProvider={leg.best_provider} />
        ) : null}
        {!selectable && <span className="text-sm text-muted-foreground">최신 가격 없음</span>}
        {leg.best_cond && <CondPriceTag price={leg.best_cond.price} label={leg.best_cond.label} />}
      </div>
    </>
  );

  const rowCls = "flex w-full flex-col gap-2 px-4 pt-3 text-left sm:flex-row sm:items-start sm:justify-between sm:gap-4";

  return (
    <li
      id={legDomId(direction, leg.flight_key)}
      className={cn(
        "scroll-mt-20 rounded-2xl border bg-card text-card-foreground transition-shadow",
        highlighted ? "ring-2 ring-amber-500" : selected && "ring-2 ring-primary",
        !selectable && "opacity-60",
      )}
    >
      {selectable ? (
        <button type="button" aria-pressed={selected} onClick={onSelect} className={cn(rowCls, "rounded-t-2xl")}>
          {summary}
        </button>
      ) : (
        <div className={rowCls}>{summary}</div>
      )}
      <div className="flex justify-end px-2">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          className="h-9 px-2 text-sm text-muted-foreground hover:text-foreground"
        >
          {open ? "상세 ▴" : "상세 ▾"}
        </button>
      </div>
      {open && (
        <div className="space-y-2 border-t px-4 py-3 text-sm">
          <p className="text-muted-foreground">편명 {leg.flight_numbers.join(", ") || "-"}</p>
          {leg.prices.map((p) => (
            <div key={p.provider} className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className={cn("inline-flex min-w-0 items-center gap-1.5", p.stale && "opacity-50")}>
                  <ProviderBadge provider={p.provider} />
                  <span className="truncate">{providerLabel(p.provider)}</span>
                  {p.price != null ? <Money value={p.price} className="shrink-0" /> : <span>-</span>}
                </span>
                <span className="inline-flex shrink-0 items-center gap-2">
                  {p.stale && <StaleBadge observedAt={p.observed_at} />}
                  {p.booking_url && (
                    <a href={p.booking_url} target="_blank" rel="noopener noreferrer" className={linkCls}>
                      {p.provider === "naver" ? "판매사 선택" : "예약"} ↗
                    </a>
                  )}
                </span>
              </div>
              {p.cond_price != null && (
                <div className="flex items-center justify-between gap-2 pl-2 text-muted-foreground">
                  <span className="flex min-w-0 items-center gap-1">
                    <span className="shrink-0">└</span>
                    {p.cond_label && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="truncate">{p.cond_label}</span>
                        </TooltipTrigger>
                        <TooltipContent>{p.cond_label}</TooltipContent>
                      </Tooltip>
                    )}
                    <Money value={p.cond_price} className="shrink-0 text-foreground" />
                  </span>
                  {p.cond_booking_url && (
                    <a href={p.cond_booking_url} target="_blank" rel="noopener noreferrer" className={linkCls}>
                      판매사 선택 ↗
                    </a>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </li>
  );
}
