import React, { useEffect, useState } from "react";
import { fetchResults } from "../api";
import type { Deal, DestinationGroup } from "../types";

function formatDuration(min: number | null) {
  if (min == null) return "-";
  return `${Math.floor(min / 60)}h ${min % 60}m`;
}

/** "2026-05-01" → "05.01" */
function formatDate(d: string) {
  const parts = d.split("-");
  return `${parts[1]}.${parts[2]}`;
}

/** "AM 10:30" / "PM 3:10" → "10:30" / "15:10" */
function normalizeTime(t: string | null) {
  if (!t) return "??:??";
  const m = t.match(/^(AM|PM)\s*(\d+):(\d+)/i);
  if (!m) return t.trim();
  let h = parseInt(m[2]);
  const min = m[3];
  if (m[1].toUpperCase() === "PM" && h !== 12) h += 12;
  if (m[1].toUpperCase() === "AM" && h === 12) h = 0;
  return `${String(h).padStart(2, "0")}:${min}`;
}

/** 시간 문자열에서 hour 추출 */
function extractHour(t: string | null): number | null {
  const norm = normalizeTime(t);
  if (norm === "??:??") return null;
  const h = parseInt(norm.split(":")[0]);
  return isNaN(h) ? null : h;
}

function timeBucket(hour: number | null): string {
  if (hour == null) return "unknown";
  if (hour < 9) return "early";
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}

function selectDiverseDeals(deals: Deal[]): Deal[] {
  const bucketMap = new Map<string, Deal[]>();
  const noTime: Deal[] = [];

  for (const deal of deals) {
    const outH = extractHour(deal.out_dep_time);
    const inH = extractHour(deal.in_dep_time);
    if (outH == null && inH == null) {
      noTime.push(deal);
      continue;
    }
    const key = `${timeBucket(outH)}_${timeBucket(inH)}`;
    if (!bucketMap.has(key)) bucketMap.set(key, []);
    bucketMap.get(key)!.push(deal);
  }

  const result: Deal[] = [];
  const seen = new Set<number>();

  for (const [, bucket] of bucketMap) {
    for (const d of bucket) {
      if (!seen.has(deals.indexOf(d))) {
        seen.add(deals.indexOf(d));
        result.push(d);
        break;
      }
    }
  }

  if (result.length < 15) {
    for (const [, bucket] of bucketMap) {
      if (result.length >= 15) break;
      for (const d of bucket) {
        const idx = deals.indexOf(d);
        if (!seen.has(idx)) {
          seen.add(idx);
          result.push(d);
          break;
        }
      }
    }
  }

  for (const d of noTime) {
    if (result.length >= 15) break;
    result.push(d);
  }

  result.sort((a, b) => a.min_price - b.min_price);
  return result;
}

function StopsBadge({ stops }: { stops: number | null }) {
  if (stops == null) return null;
  return stops === 0 ? (
    <span className="text-[10px] bg-apple-green/10 text-apple-green px-2 py-0.5 rounded-full font-medium whitespace-nowrap">직항</span>
  ) : (
    <span className="text-[10px] bg-apple-orange/10 text-apple-orange px-2 py-0.5 rounded-full font-medium whitespace-nowrap">{stops}경유</span>
  );
}

function CheckedAtLabel({ checkedAt }: { checkedAt: string }) {
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

const TRIP_TYPE_OPTIONS: { label: string; value?: string }[] = [
  { label: "전체" },
  { label: "왕복", value: "round_trip" },
  { label: "편도조합", value: "oneway_combo" },
];

function TripTypeBadge({ tripType }: { tripType: string }) {
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

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  google_flights: { label: "Google", color: "bg-apple-blue/10 text-apple-blue" },
  amadeus:        { label: "Amadeus", color: "bg-apple-orange/10 text-apple-orange" },
  naver:          { label: "네이버", color: "bg-apple-green/10 text-apple-green" },
  skyscanner:     { label: "Skyscanner", color: "bg-sky-100 text-sky-600" },
};

function SourceBadge({ source }: { source: string }) {
  const info = SOURCE_LABELS[source] ?? { label: source, color: "bg-gray-100 text-gray-500" };
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${info.color}`}>
      {info.label}
    </span>
  );
}

/** 구간 한 줄 (데스크탑) / 세로 스택 (모바일) */
function LegRow({ leg, isMixed, index }: {
  leg: { airline: string; dep: string | null; arr: string | null; dur: number | null; stops: number | null; from: string; to: string; date: string; url: string | null; urlLabel: string };
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
        {leg.url && (
          <a href={leg.url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-apple-blue hover:underline">
            {leg.urlLabel} ↗
          </a>
        )}
      </div>
    </div>
  );
}

function DealCard({ deal, rank }: { deal: Deal; rank: number }) {
  const legs = [
    { airline: deal.out_airline, dep: deal.out_dep_time, arr: deal.out_arr_time, dur: deal.out_duration_min, stops: deal.out_stops, from: deal.origin, to: (deal.out_arr_airport && deal.out_arr_airport !== deal.origin) ? deal.out_arr_airport : deal.destination, date: deal.departure_date, url: deal.out_url, urlLabel: deal.out_url?.includes("/booking?") ? "출발편 예약" : "출발편 검색" },
    { airline: deal.in_airline, dep: deal.in_dep_time, arr: deal.in_arr_time, dur: deal.in_duration_min, stops: deal.in_stops, from: deal.in_dep_airport || deal.destination, to: deal.origin, date: deal.return_date, url: deal.in_url, urlLabel: deal.in_url?.includes("/booking?") ? "복귀편 예약" : "복귀편 검색" },
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

function getMonthOptions(): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let offset = 0; offset <= 12; offset++) {
    const d = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return months;
}

function formatMonth(m: string) {
  return `${parseInt(m.split("-")[1])}월`;
}

function MonthFilter({ activeMonth, onChange }: { activeMonth: string; onChange: (m: string) => void }) {
  const months = getMonthOptions();
  return (
    <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
      <div className="flex gap-1.5 w-max sm:w-auto sm:flex-wrap">
        {months.map((m) => (
          <button
            key={m}
            onClick={() => onChange(m)}
            className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all duration-200 whitespace-nowrap ${
              activeMonth === m
                ? "bg-apple-text text-white"
                : "bg-white text-apple-secondary hover:text-apple-text shadow-apple-sm"
            }`}
          >
            {formatMonth(m)}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Results() {
  const [groups, setGroups] = useState<DestinationGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeDest, setActiveDest] = useState<string | null>(null);
  const [activeTripType, setActiveTripType] = useState<string | undefined>(undefined);
  const [activeMonth, setActiveMonth] = useState<string>(() => getMonthOptions()[0]);

  const load = (month?: string) => {
    setLoading(true);
    setError("");
    fetchResults({ month })
      .then((data) => {
        setGroups(data);
        if (data.length > 0 && (!activeDest || !data.find((g) => g.destination === activeDest))) {
          setActiveDest(data[0].destination);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(activeMonth); }, [activeMonth]);

  if (loading)
    return <div className="flex items-center justify-center py-20 text-apple-secondary text-base">로딩 중…</div>;

  if (error)
    return (
      <div className="flex flex-col items-center py-20 gap-4 text-apple-red">
        <p className="text-base">{error}</p>
        <button onClick={() => load(activeMonth)} className="px-4 py-2 bg-apple-red/10 rounded-full text-sm hover:bg-apple-red/20 transition-colors">재시도</button>
      </div>
    );

  if (groups.length === 0)
    return (
      <div className="space-y-6">
        <MonthFilter activeMonth={activeMonth} onChange={setActiveMonth} />
        <div className="flex flex-col items-center py-20 gap-3 text-apple-secondary">
          <p className="text-5xl">✈</p>
          <p className="text-lg font-medium">해당 월의 항공권 데이터가 없습니다.</p>
          <p className="text-sm">다른 월을 선택하거나 수집을 실행해주세요.</p>
        </div>
      </div>
    );

  const activeGroup = groups.find((g) => g.destination === activeDest) ?? groups[0];

  const filteredDeals = activeTripType
    ? activeGroup.deals.filter((d) => d.trip_type === activeTripType)
    : activeGroup.deals;

  const topDeals = filteredDeals.slice(0, 5);
  const restDeals = selectDiverseDeals(filteredDeals.slice(5));

  const minPrice = filteredDeals.length > 0
    ? Math.min(...filteredDeals.map((d) => d.min_price))
    : 0;

  return (
    <div className="space-y-5">
      {/* 월 필터 */}
      <MonthFilter activeMonth={activeMonth} onChange={setActiveMonth} />

      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-apple-secondary">{groups.length}개 여행지</p>
        <button onClick={() => load(activeMonth)} className="text-xs text-apple-blue hover:underline">새로고침</button>
      </div>

      {/* 목적지 탭 — 가로 스크롤 */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2 w-max sm:w-auto sm:flex-wrap">
          {groups.map((g) => {
            const gMin = Math.min(...g.deals.map((d) => d.min_price));
            const isActive = g.destination === activeGroup.destination;
            return (
              <button
                key={g.destination}
                onClick={() => setActiveDest(g.destination)}
                className={`flex flex-col items-start px-4 py-2.5 rounded-2xl text-left transition-all duration-200 whitespace-nowrap ${
                  isActive
                    ? "bg-apple-text text-white shadow-apple"
                    : "bg-white text-apple-text shadow-apple-sm hover:shadow-apple"
                }`}
              >
                <span className="text-sm font-semibold">{g.destination_name}</span>
                <span className={`text-[11px] ${isActive ? "text-white/60" : "text-apple-secondary"}`}>
                  {g.destination} · {Math.round(gMin).toLocaleString()}원~
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 선택된 목적지 헤더 + trip_type 필터 */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl sm:text-2xl font-bold text-apple-text">{activeGroup.destination_name}</h2>
          <span className="text-sm text-apple-secondary">{activeGroup.destination}</span>
          {minPrice > 0 && (
            <span className="text-sm font-semibold text-apple-blue whitespace-nowrap">
              최저 {Math.round(minPrice).toLocaleString()}원~
            </span>
          )}
        </div>
        <div className="flex gap-1.5 sm:ml-auto">
          {TRIP_TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.label}
              onClick={() => setActiveTripType(opt.value)}
              className={`text-xs px-3 py-1 rounded-full font-medium transition-all duration-200 ${
                activeTripType === opt.value
                  ? "bg-apple-text text-white"
                  : "bg-white text-apple-secondary shadow-apple-sm hover:text-apple-text"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {filteredDeals.length === 0 ? (
        <div className="text-center py-10 text-apple-secondary text-sm">해당 조건의 항공권이 없습니다.</div>
      ) : (
        <>
          <section>
            <h3 className="text-base font-semibold text-apple-text mb-3">오늘의 최저가</h3>
            <div className="flex flex-col gap-3">
              {topDeals.map((deal, i) => (
                <DealCard key={i} deal={deal} rank={i + 1} />
              ))}
            </div>
          </section>

          {restDeals.length > 0 && (
            <section>
              <h3 className="text-base font-semibold text-apple-text mb-3">시간대별 추천</h3>
              <div className="flex flex-col gap-3">
                {restDeals.map((deal, i) => (
                  <DealCard key={i} deal={deal} rank={i + 6} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
