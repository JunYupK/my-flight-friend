import React from "react";
import type { Deal } from "../types";
import { formatDate, normalizeTime, formatDuration } from "../utils";

export function StopsBadge({ stops }: { stops: number | null }) {
  if (stops == null) return null;
  return stops === 0 ? (
    <span className="text-[10px] bg-apple-green/10 text-apple-green px-2 py-0.5 rounded-full font-medium whitespace-nowrap">직항</span>
  ) : (
    <span className="text-[10px] bg-apple-orange/10 text-apple-orange px-2 py-0.5 rounded-full font-medium whitespace-nowrap">{stops}경유</span>
  );
}

export function CheckedAtLabel({ checkedAt }: { checkedAt: string }) {
  const d = new Date(checkedAt);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return (
    <span className="text-[10px] text-apple-tertiary">
      {mm}.{dd} {hh}:{mi} 수집
    </span>
  );
}

export const TRIP_TYPE_OPTIONS: { label: string; value?: string }[] = [
  { label: "전체" },
  { label: "왕복", value: "round_trip" },
  { label: "편도조합", value: "oneway_combo" },
];

export function TripTypeBadge({ tripType }: { tripType: string }) {
  if (tripType === "oneway_combo") {
    return (
      <span className="text-[10px] bg-apple-purple/10 text-apple-purple px-2 py-0.5 rounded-full font-medium">
        편도+편도
      </span>
    );
  }
  return (
    <span className="text-[10px] bg-apple-blue/10 text-apple-blue px-2 py-0.5 rounded-full font-medium">
      왕복
    </span>
  );
}

export const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  google_flights: { label: "Google", color: "bg-apple-blue/10 text-apple-blue" },
  amadeus:        { label: "Amadeus", color: "bg-apple-orange/10 text-apple-orange" },
  naver:          { label: "네이버", color: "bg-apple-green/10 text-apple-green" },
  skyscanner:     { label: "Skyscanner", color: "bg-sky-100 text-sky-600" },
};

export function SourceBadge({ source }: { source: string }) {
  const info = SOURCE_LABELS[source] ?? { label: source, color: "bg-gray-100 text-gray-500" };
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${info.color}`}>
      {info.label}
    </span>
  );
}

/** 구간 한 줄 (데스크탑) / 세로 스택 (모바일) */
export function LegRow({ leg, isMixed, index }: {
  leg: { airline: string; dep: string | null; arr: string | null; dur: number | null; stops: number | null; from: string; to: string; date: string; url: string | null; urlLabel: string; price: number | null };
  isMixed: boolean;
  index: number;
}) {
  return (
    <div className={`px-4 py-3 ${index === 0 ? "border-t border-apple-tertiary/20" : "border-t border-dashed border-apple-tertiary/20"}`}>
      {/* 데스크탑: 한 줄 */}
      <div className="hidden sm:flex items-center gap-3">
        <span className={`text-sm font-medium w-16 shrink-0 truncate ${isMixed ? "text-apple-orange" : "text-apple-text"}`}>
          {leg.airline}
        </span>
        <div className="flex flex-col min-w-0">
          <span className="text-sm font-semibold text-apple-text whitespace-nowrap">
            {normalizeTime(leg.dep)} → {normalizeTime(leg.arr)}
          </span>
          <span className="text-[11px] text-apple-secondary">{leg.from} → {leg.to} · {formatDate(leg.date)}</span>
        </div>
        <span className="text-xs text-apple-secondary whitespace-nowrap shrink-0 ml-auto">{formatDuration(leg.dur)}</span>
        <StopsBadge stops={leg.stops} />
        {leg.price != null && (
          <span className="text-xs font-semibold text-apple-text whitespace-nowrap shrink-0">
            {Math.round(leg.price).toLocaleString()}원
          </span>
        )}
        {leg.url && (
          <a href={leg.url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-apple-blue hover:underline whitespace-nowrap shrink-0">
            {leg.urlLabel} ↗
          </a>
        )}
      </div>

      {/* 모바일: 세로 스택 */}
      <div className="flex sm:hidden flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <span className={`text-sm font-medium ${isMixed ? "text-apple-orange" : "text-apple-text"}`}>
            {leg.airline}
          </span>
          <div className="flex items-center gap-1.5">
            <StopsBadge stops={leg.stops} />
            <span className="text-[11px] text-apple-secondary">{formatDuration(leg.dur)}</span>
          </div>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-apple-text">
            {normalizeTime(leg.dep)} → {normalizeTime(leg.arr)}
          </span>
          <span className="text-[11px] text-apple-secondary">{leg.from}→{leg.to} · {formatDate(leg.date)}</span>
        </div>
        <div className="flex items-center gap-2">
          {leg.price != null && (
            <span className="text-xs font-semibold text-apple-text">
              {Math.round(leg.price).toLocaleString()}원
            </span>
          )}
          {leg.url && (
            <a href={leg.url} target="_blank" rel="noopener noreferrer"
              className="text-xs text-apple-blue hover:underline">
              {leg.urlLabel} ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export function DealCard({ deal, rank }: { deal: Deal; rank: number }) {
  const legs = [
    { airline: deal.out_airline, dep: deal.out_dep_time, arr: deal.out_arr_time, dur: deal.out_duration_min, stops: deal.out_stops, from: deal.origin, to: (deal.out_arr_airport && deal.out_arr_airport !== deal.origin) ? deal.out_arr_airport : deal.destination, date: deal.departure_date, url: deal.out_url, urlLabel: deal.out_url?.includes("/booking?") ? "출발편 예약" : "출발편 검색", price: deal.out_price },
    { airline: deal.in_airline, dep: deal.in_dep_time, arr: deal.in_arr_time, dur: deal.in_duration_min, stops: deal.in_stops, from: (deal.in_dep_airport && deal.in_dep_airport !== deal.origin) ? deal.in_dep_airport : deal.destination, to: deal.origin, date: deal.return_date, url: deal.in_url, urlLabel: deal.in_url?.includes("/booking?") ? "복귀편 예약" : "복귀편 검색", price: deal.in_price },
  ];

  return (
    <div className="bg-white rounded-2xl shadow-apple-sm hover:shadow-apple transition-all duration-200">
      {/* 헤더 */}
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 px-4 pt-3 pb-2">
        <span className="text-xs font-bold text-apple-tertiary">#{rank}</span>
        <span className="text-sm font-semibold text-apple-text">
          {formatDate(deal.departure_date)} → {formatDate(deal.return_date)}
        </span>
        <span className="text-xs font-medium text-apple-blue">{deal.stay_nights}박</span>
        <SourceBadge source={deal.source} />
        <TripTypeBadge tripType={deal.trip_type} />
        {deal.last_checked_at && <CheckedAtLabel checkedAt={deal.last_checked_at} />}
      </div>

      {/* 구간 */}
      {legs.map((leg, i) => (
        <LegRow key={i} leg={leg} isMixed={i === 1 && !!deal.is_mixed_airline} index={i} />
      ))}

      {/* 가격 */}
      <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-apple-tertiary/20">
        {!!deal.is_mixed_airline && <span className="text-[11px] text-apple-orange">(혼합 항공사)</span>}
        <span className="text-2xl font-bold text-apple-text tracking-tight">
          {Math.round(deal.min_price).toLocaleString()}
        </span>
        <span className="text-sm text-apple-secondary">원</span>
      </div>
    </div>
  );
}
