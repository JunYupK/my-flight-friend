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

function StopsBadge({ stops }: { stops: number | null }) {
  if (stops == null) return null;
  return stops === 0 ? (
    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-semibold whitespace-nowrap shrink-0">직항</span>
  ) : (
    <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full font-semibold whitespace-nowrap shrink-0">{stops}경유</span>
  );
}

function DealCard({ deal, rank }: { deal: Deal; rank: number }) {
  const airline =
    deal.out_airline === deal.in_airline
      ? deal.out_airline
      : `${deal.out_airline} / ${deal.in_airline}`;

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 hover:shadow-lg transition-shadow flex flex-col gap-4">
      {/* 순위 + 가격 */}
      <div className="flex items-start justify-between">
        <span className="text-sm font-bold text-gray-300">#{rank}</span>
        <div className="text-right">
          <p className="text-3xl font-extrabold text-blue-600 leading-none">
            {Math.round(deal.min_price).toLocaleString()}
          </p>
          <p className="text-sm text-gray-400 mt-1">원 · 왕복</p>
        </div>
      </div>

      {/* 날짜 + 체류 + 공항 */}
      <div className="bg-gray-50 rounded-xl px-3 py-2 space-y-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold text-blue-500">
            {deal.origin}
          </span>
          <span className="text-xs text-gray-300">✈</span>
          <span className="text-xs font-bold text-blue-500">
            {deal.out_arr_airport ?? deal.destination}
          </span>
          {deal.out_arr_airport && deal.in_dep_airport && deal.out_arr_airport !== deal.in_dep_airport && (
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

      {/* 항공사 + 출처 */}
      <div className="flex items-center justify-between pt-1 border-t border-gray-100">
        <span className={`text-sm font-medium leading-snug ${deal.is_mixed_airline ? "text-orange-500" : "text-gray-600"}`}>
          {airline}
          {deal.is_mixed_airline && <span className="ml-1 text-xs text-orange-400">(혼합)</span>}
        </span>
        <span className="text-xs text-gray-300 shrink-0 ml-2">
          {deal.source === "google_flights" ? "Google" : deal.source}
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

function DestinationSection({ group }: { group: DestinationGroup }) {
  const minPrice = Math.min(...group.deals.map((d) => d.min_price));

  return (
    <section>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-4">
        <h2 className="text-2xl font-bold text-gray-800">{group.destination_name}</h2>
        <span className="text-base text-gray-400">{group.destination}</span>
        <span className="ml-auto text-base font-semibold text-blue-500 whitespace-nowrap">
          최저 {Math.round(minPrice).toLocaleString()}원~
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
        {group.deals.map((deal, i) => (
          <DealCard key={i} deal={deal} rank={i + 1} />
        ))}
      </div>
    </section>
  );
}

export default function Results() {
  const [groups, setGroups] = useState<DestinationGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    fetchResults()
      .then(setGroups)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (loading)
    return <div className="flex items-center justify-center py-20 text-gray-400 text-lg">로딩 중…</div>;

  if (error)
    return (
      <div className="flex flex-col items-center py-20 gap-4 text-red-500">
        <p className="text-base">{error}</p>
        <button onClick={load} className="px-4 py-2 bg-red-50 rounded-lg text-sm hover:bg-red-100">재시도</button>
      </div>
    );

  if (groups.length === 0)
    return (
      <div className="flex flex-col items-center py-20 gap-3 text-gray-400">
        <p className="text-5xl">✈</p>
        <p className="text-lg">수집된 항공권 데이터가 없습니다.</p>
        <p className="text-sm">설정에서 수집을 실행해주세요.</p>
      </div>
    );

  return (
    <div className="space-y-12">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">{groups.length}개 여행지 · 여행지별 최저가 Top 5</p>
        <button onClick={load} className="text-sm text-blue-500 hover:text-blue-700">새로고침</button>
      </div>
      {groups.map((g) => (
        <DestinationSection key={g.destination} group={g} />
      ))}
    </div>
  );
}
