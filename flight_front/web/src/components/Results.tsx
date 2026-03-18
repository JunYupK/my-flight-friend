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

/** 시간 문자열에서 hour 추출 (normalizeTime 결과 기준) */
function extractHour(t: string | null): number | null {
  const norm = normalizeTime(t);
  if (norm === "??:??") return null;
  const h = parseInt(norm.split(":")[0]);
  return isNaN(h) ? null : h;
}

/** hour → 시간대 버킷 */
function timeBucket(hour: number | null): string {
  if (hour == null) return "unknown";
  if (hour < 9) return "early";    // 05-09
  if (hour < 12) return "morning"; // 09-12
  if (hour < 17) return "afternoon"; // 12-17
  return "evening";                // 17-22+
}

/** 시간대 다양성 기반으로 deals에서 ~15개 선별 */
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

  // 각 버킷에서 최저가 1개씩
  for (const [, bucket] of bucketMap) {
    for (const d of bucket) {
      if (!seen.has(deals.indexOf(d))) {
        seen.add(deals.indexOf(d));
        result.push(d);
        break;
      }
    }
  }

  // 15개 미만이면 각 버킷에서 다음 미선택 항목 추가
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

  // 시간 정보 없는 deal 추가 (최대 3개)
  for (const d of noTime) {
    if (result.length >= 15) break;
    result.push(d);
  }

  // 가격순 정렬
  result.sort((a, b) => a.min_price - b.min_price);
  return result;
}

function StopsBadge({ stops }: { stops: number | null }) {
  if (stops == null) return null;
  return stops === 0 ? (
    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-semibold whitespace-nowrap shrink-0">직항</span>
  ) : (
    <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full font-semibold whitespace-nowrap shrink-0">{stops}경유</span>
  );
}

/** 수집 일시를 "MM.DD HH:mm 수집" 형태로 표시 */
function CheckedAtLabel({ checkedAt }: { checkedAt: string }) {
  const d = new Date(checkedAt);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return (
    <span className="text-xs text-gray-400">
      {mm}.{dd} {hh}:{mi} 수집
    </span>
  );
}

const TRIP_TYPE_OPTIONS: { label: string; value?: string }[] = [
  { label: "전체" },
  { label: "왕복 검색", value: "round_trip" },
  { label: "편도 조합", value: "oneway_combo" },
];

function TripTypeBadge({ tripType }: { tripType: string }) {
  if (tripType === "oneway_combo") {
    return (
      <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">
        편도+편도
      </span>
    );
  }
  return (
    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
      왕복
    </span>
  );
}

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  google_flights: { label: "Google Flights", color: "bg-blue-500 text-white" },
  amadeus:        { label: "Amadeus",        color: "bg-amber-500 text-white" },
  naver:          { label: "네이버 항공권",    color: "bg-green-500 text-white" },
  skyscanner:     { label: "Skyscanner",     color: "bg-sky-500 text-white" },
};

function SourceBadge({ source }: { source: string }) {
  const info = SOURCE_LABELS[source] ?? { label: source, color: "bg-gray-500 text-white" };
  return (
    <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${info.color}`}>
      {info.label}
    </span>
  );
}

function DealCard({ deal, rank }: { deal: Deal; rank: number }) {
  const airline =
    deal.out_airline === deal.in_airline
      ? deal.out_airline
      : `${deal.out_airline} / ${deal.in_airline}`;

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 hover:shadow-lg transition-shadow flex flex-col gap-4">
      {/* 순위 + 출처 + 가격 */}
      <div className="flex items-start justify-between">
        <span className="text-sm font-bold text-gray-300">#{rank}</span>
        <SourceBadge source={deal.source} />
        <div className="text-right">
          <p className="text-3xl font-extrabold text-blue-600 leading-none">
            {Math.round(deal.min_price).toLocaleString()}
          </p>
          <div className="flex items-center gap-1.5 mt-1 justify-end">
            <span className="text-sm text-gray-400">원 · 왕복</span>
            <TripTypeBadge tripType={deal.trip_type} />
          </div>
          {deal.last_checked_at && (
            <div className="mt-1">
              <CheckedAtLabel checkedAt={deal.last_checked_at} />
            </div>
          )}
        </div>
      </div>

      {/* 날짜 + 체류 + 공항 */}
      <div className="bg-gray-50 rounded-xl px-3 py-2 space-y-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold text-blue-500">
            {deal.origin}
          </span>
          <span className="text-xs text-gray-300">→</span>
          <span className="text-xs font-bold text-blue-500">
            {(deal.out_arr_airport && deal.out_arr_airport !== deal.origin) ? deal.out_arr_airport : deal.destination}
          </span>
          {deal.out_arr_airport && deal.in_dep_airport
            && deal.out_arr_airport !== deal.origin && deal.in_dep_airport !== deal.origin
            && deal.out_arr_airport !== deal.in_dep_airport && (
            <span className="text-xs text-orange-400 ml-1">
              복귀:{deal.in_dep_airport}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-semibold text-gray-700">{formatDate(deal.departure_date)}</span>
          <span className="text-gray-300">→</span>
          <span className="text-sm font-semibold text-gray-700">{formatDate(deal.return_date)}</span>
          <span className="ml-auto text-sm font-medium text-blue-500 shrink-0 whitespace-nowrap">{deal.stay_nights}박</span>
        </div>
      </div>

      {/* 항공편 */}
      <div className="space-y-2.5">
        {[
          { label: "출발 ↗", dep: deal.out_dep_time, arr: deal.out_arr_time, dur: deal.out_duration_min, stops: deal.out_stops },
          { label: "복귀 ↙", dep: deal.in_dep_time,  arr: deal.in_arr_time,  dur: deal.in_duration_min,  stops: deal.in_stops  },
        ].map((leg, i) => (
          <React.Fragment key={i}>
            {i === 1 && <div className="border-t border-dashed border-gray-100" />}
            <div className="flex items-center gap-x-2 min-w-0">
              <span className="text-xs text-gray-400 w-10 shrink-0">{leg.label}</span>
              <span className="text-sm font-semibold text-gray-800 whitespace-nowrap flex-1 min-w-0">
                {normalizeTime(leg.dep)} → {normalizeTime(leg.arr)}
              </span>
              <span className="text-xs text-gray-400 whitespace-nowrap shrink-0">{formatDuration(leg.dur)}</span>
              <StopsBadge stops={leg.stops} />
            </div>
          </React.Fragment>
        ))}
      </div>

      {/* 항공사 */}
      <div className="pt-1 border-t border-gray-100">
        <span className={`text-sm font-medium leading-snug ${!!deal.is_mixed_airline ? "text-orange-500" : "text-gray-600"}`}>
          {airline}
          {!!deal.is_mixed_airline && <span className="ml-1 text-xs text-orange-400">(혼합)</span>}
        </span>
      </div>

      {/* 바로가기 링크 */}
      {(deal.out_url || deal.in_url) && (
        <div className="flex gap-2 pt-1">
          {deal.out_url && (
            <a
              href={deal.out_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 text-center text-xs py-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 font-medium transition-colors"
            >
              출발편 검색 ↗
            </a>
          )}
          {deal.in_url && (
            <a
              href={deal.in_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 text-center text-xs py-1.5 rounded-lg bg-gray-50 text-gray-500 hover:bg-gray-100 font-medium transition-colors"
            >
              복귀편 검색 ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/** 현재 월 기준 +12개월 목록 */
function getMonthOptions(): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let offset = 0; offset <= 12; offset++) {
    const d = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return months;
}

/** "2026-03" → "3월" */
function formatMonth(m: string) {
  return `${parseInt(m.split("-")[1])}월`;
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
    return <div className="flex items-center justify-center py-20 text-gray-400 text-lg">로딩 중…</div>;

  if (error)
    return (
      <div className="flex flex-col items-center py-20 gap-4 text-red-500">
        <p className="text-base">{error}</p>
        <button onClick={() => load(activeMonth)} className="px-4 py-2 bg-red-50 rounded-lg text-sm hover:bg-red-100">재시도</button>
      </div>
    );

  if (groups.length === 0)
    return (
      <div className="space-y-6">
        {/* 월 필터는 데이터 없어도 표시 */}
        <MonthFilter activeMonth={activeMonth} onChange={setActiveMonth} />
        <div className="flex flex-col items-center py-20 gap-3 text-gray-400">
          <p className="text-5xl">✈</p>
          <p className="text-lg">해당 월의 항공권 데이터가 없습니다.</p>
          <p className="text-sm">다른 월을 선택하거나 수집을 실행해주세요.</p>
        </div>
      </div>
    );

  const activeGroup = groups.find((g) => g.destination === activeDest) ?? groups[0];

  // trip_type 필터 적용
  const filteredDeals = activeTripType
    ? activeGroup.deals.filter((d) => d.trip_type === activeTripType)
    : activeGroup.deals;

  // 상위 5개: 오늘의 최저가
  const topDeals = filteredDeals.slice(0, 5);
  // 나머지에서 시간대 다양성 기반 ~15개 선별
  const restDeals = selectDiverseDeals(filteredDeals.slice(5));

  const minPrice = filteredDeals.length > 0
    ? Math.min(...filteredDeals.map((d) => d.min_price))
    : 0;

  return (
    <div className="space-y-6">
      {/* 월 필터 */}
      <MonthFilter activeMonth={activeMonth} onChange={setActiveMonth} />

      {/* 헤더 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-gray-400">{groups.length}개 여행지</p>
        <button onClick={() => load(activeMonth)} className="text-sm text-blue-500 hover:text-blue-700">새로고침</button>
      </div>

      {/* 목적지 탭 */}
      <div className="flex flex-wrap gap-2">
        {groups.map((g) => {
          const gMin = Math.min(...g.deals.map((d) => d.min_price));
          const isActive = g.destination === activeGroup.destination;
          return (
            <button
              key={g.destination}
              onClick={() => setActiveDest(g.destination)}
              className={`flex flex-col items-start px-4 py-2.5 rounded-xl text-left transition-all ${
                isActive
                  ? "bg-blue-600 text-white shadow-md"
                  : "bg-white border border-gray-200 text-gray-700 hover:border-blue-300 hover:shadow-sm"
              }`}
            >
              <span className="text-sm font-bold">{g.destination_name}</span>
              <span className={`text-xs ${isActive ? "text-blue-100" : "text-gray-400"}`}>
                {g.destination} · {Math.round(gMin).toLocaleString()}원~
              </span>
            </button>
          );
        })}
      </div>

      {/* 선택된 목적지 헤더 + trip_type 필터 */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-bold text-gray-800">{activeGroup.destination_name}</h2>
        <span className="text-base text-gray-400">{activeGroup.destination}</span>
        {minPrice > 0 && (
          <span className="text-base font-semibold text-blue-500 whitespace-nowrap">
            최저 {Math.round(minPrice).toLocaleString()}원~
          </span>
        )}
        <div className="ml-auto flex gap-1.5">
          {TRIP_TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.label}
              onClick={() => setActiveTripType(opt.value)}
              className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${
                activeTripType === opt.value
                  ? "bg-purple-500 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {filteredDeals.length === 0 ? (
        <div className="text-center py-10 text-gray-400 text-sm">해당 조건의 항공권이 없습니다.</div>
      ) : (
        <>
          {/* 오늘의 최저가 섹션 */}
          <section>
            <h3 className="text-lg font-bold text-gray-700 mb-3">오늘의 최저가</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
              {topDeals.map((deal, i) => (
                <DealCard key={i} deal={deal} rank={i + 1} />
              ))}
            </div>
          </section>

          {/* 모든 항공권 조합 섹션 */}
          {restDeals.length > 0 && (
            <section>
              <h3 className="text-lg font-bold text-gray-700 mb-3">시간대별 추천</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
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

function MonthFilter({ activeMonth, onChange }: { activeMonth: string; onChange: (m: string) => void }) {
  const months = getMonthOptions();
  return (
    <div className="flex flex-wrap gap-1.5">
      {months.map((m) => (
        <button
          key={m}
          onClick={() => onChange(m)}
          className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
            activeMonth === m
              ? "bg-blue-600 text-white"
              : "bg-white border border-gray-200 text-gray-600 hover:border-blue-300"
          }`}
        >
          {formatMonth(m)}
        </button>
      ))}
    </div>
  );
}
