import React, { useEffect, useState } from "react";
import { fetchResults } from "../api";
import type { DestinationGroup } from "../types";
import { DealCard, TRIP_TYPE_OPTIONS } from "./DealCard";

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
  const [year, month] = m.split("-");
  return `${year}년 ${parseInt(month)}월`;
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

  const load = (month?: string, tripType?: string) => {
    setLoading(true);
    setError("");
    fetchResults({ month, trip_type: tripType })
      .then((data) => {
        setGroups(data);
        if (data.length > 0 && (!activeDest || !data.find((g) => g.destination === activeDest))) {
          setActiveDest(data[0].destination);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(activeMonth, activeTripType); }, [activeMonth, activeTripType]);

  if (loading)
    return <div className="flex items-center justify-center py-20 text-apple-secondary text-base">로딩 중…</div>;

  if (error)
    return (
      <div className="flex flex-col items-center py-20 gap-4 text-apple-red">
        <p className="text-base">{error}</p>
        <button onClick={() => load(activeMonth, activeTripType)} className="px-4 py-2 bg-apple-red/10 rounded-full text-sm hover:bg-apple-red/20 transition-colors">재시도</button>
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

  return (
    <div className="space-y-5">
      {/* 월 필터 */}
      <MonthFilter activeMonth={activeMonth} onChange={setActiveMonth} />

      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-apple-secondary">{groups.length}개 여행지</p>
        <button onClick={() => load(activeMonth, activeTripType)} className="text-xs text-apple-blue hover:underline">새로고침</button>
      </div>

      {/* 목적지 탭 — 가로 스크롤 */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2 w-max sm:w-auto sm:flex-wrap">
          {groups.map((g) => {
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
                  {g.destination} · {Math.round(g.min_price).toLocaleString()}원~
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
          {activeGroup.min_price > 0 && (
            <span className="text-sm font-semibold text-apple-blue whitespace-nowrap">
              최저 {Math.round(activeGroup.min_price).toLocaleString()}원~
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

      {activeGroup.total_count === 0 ? (
        <div className="text-center py-10 text-apple-secondary text-sm">해당 조건의 항공권이 없습니다.</div>
      ) : (
        <>
          <section>
            <h3 className="text-base font-semibold text-apple-text mb-3">오늘의 최저가</h3>
            <div className="flex flex-col gap-3">
              {activeGroup.top_deals.map((deal, i) => (
                <DealCard key={i} deal={deal} rank={i + 1} />
              ))}
            </div>
          </section>

          {activeGroup.diverse_deals.length > 0 && (
            <section>
              <h3 className="text-base font-semibold text-apple-text mb-3">시간대별 추천</h3>
              <div className="flex flex-col gap-3">
                {activeGroup.diverse_deals.map((deal, i) => (
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
