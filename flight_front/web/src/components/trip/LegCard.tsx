import { useState } from "react";
import type { MergedLegView } from "../../types";
import { formatWon, timeAgo } from "../../utils";
import { providerLabel } from "./providers";

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

export default function LegCard({ leg, direction, selected, highlighted, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const selectable = leg.best_price != null;
  const overnight = leg.dep_time != null && leg.arr_time != null && leg.arr_time < leg.dep_time;
  const fresh = leg.prices.filter((p) => !p.stale);
  const others = fresh.length > 1 ? fresh.length - 1 : 0;
  const ring = selected
    ? "ring-2 ring-apple-blue"
    : highlighted
      ? "ring-2 ring-apple-orange"
      : "ring-1 ring-apple-text/10";

  const content = (
    <>
        <span className="block min-w-0">
          <span className="block text-lg font-semibold text-apple-text">
            {leg.dep_time ?? "--:--"} → {leg.arr_time ?? "--:--"}
            {overnight && <span className="ml-1 text-xs font-medium text-apple-orange">+1</span>}
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-apple-secondary">
            <span>{leg.airline_name ?? leg.airline_iata ?? "항공사 미상"}</span>
            {leg.stops === 0 ? (
              <span>직항</span>
            ) : leg.stops != null ? (
              <span className="text-apple-orange">경유 {leg.stops}회</span>
            ) : null}
            {leg.duration_min != null && <span>{legDuration(leg.duration_min)}</span>}
            {!leg.in_condition && selectable && <span className="text-apple-orange">조건 밖</span>}
          </span>
        </span>
        <span className="shrink-0 text-right">
          {selectable ? (
            <>
              <span className="block text-lg font-semibold text-apple-text">{formatWon(leg.best_price ?? 0)}</span>
              {leg.best_provider && (
                <span className="block text-xs text-apple-secondary">
                  {providerLabel(leg.best_provider)}
                  {others > 0 && ` 외 ${others}곳`}
                </span>
              )}
            </>
          ) : (
            <span className="text-sm text-apple-secondary">확인가 없음</span>
          )}
        </span>
    </>
  );

  return (
    <li
      id={legDomId(direction, leg.flight_key)}
      className={`rounded-xl bg-apple-surface p-3 ${ring} ${selectable ? "" : "opacity-60"} ${leg.in_condition ? "" : "border-l-4 border-apple-tertiary"}`}
    >
      {selectable ? (
        <button type="button" aria-pressed={selected} onClick={onSelect} className="flex w-full items-start justify-between gap-2 text-left">
          {content}
        </button>
      ) : (
        <div className="flex w-full items-start justify-between gap-2 text-left">{content}</div>
      )}
      <div className="mt-1 flex justify-end">
        <button
          type="button"
          aria-expanded={open}
          aria-label="상세 보기"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(!open);
          }}
          className="px-2 text-sm text-apple-secondary hover:text-apple-text"
        >
          {open ? "▴" : "▾"}
        </button>
      </div>
      {open && (
        <div className="mt-1 space-y-1 border-t border-apple-text/5 pt-2 text-xs">
          <p className="text-apple-secondary">편명 {leg.flight_numbers.join(", ") || "-"}</p>
          {leg.prices.map((p) => (
            <div
              key={p.provider}
              className={`flex flex-wrap items-center justify-between gap-x-2 ${p.stale ? "opacity-50" : ""}`}
            >
              <span className="text-apple-text">
                {providerLabel(p.provider)} {p.price != null ? formatWon(p.price) : "-"}
                {p.stale && <span className="ml-1 text-apple-orange">오래됨</span>}
              </span>
              <span className="text-apple-secondary">
                {timeAgo(p.observed_at)}
                {p.booking_url && (
                  <a
                    href={p.booking_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-2 text-apple-blue hover:underline"
                  >
                    예약 ↗
                  </a>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </li>
  );
}
