import React, { useState, useEffect } from "react";
import { searchFlights } from "../api";
import type { DestinationGroup } from "../types";
import { DAY_NAMES } from "../utils";
import { DealCard, TRIP_TYPE_OPTIONS, SOURCE_LABELS } from "./DealCard";

/* ── Calendar Picker ─────────────────────────────────── */

function CalendarPicker({
  value,
  onChange,
  minDate,
  label,
}: {
  value: string | null;
  onChange: (date: string) => void;
  minDate?: string;
  label: string;
}) {
  const [viewDate, setViewDate] = useState(() => {
    if (value) {
      const [y, m] = value.split("-").map(Number);
      return new Date(y, m - 1, 1);
    }
    return new Date(new Date().getFullYear(), new Date().getMonth(), 1);
  });

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  const prevMonth = () => setViewDate(new Date(year, month - 1, 1));
  const nextMonth = () => setViewDate(new Date(year, month + 1, 1));

  const isDisabled = (dateStr: string) => {
    if (dateStr < todayStr) return true;
    if (minDate && dateStr < minDate) return true;
    return false;
  };

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  return (
    <div className="bg-white rounded-2xl shadow-apple-sm p-4">
      <p className="text-xs font-medium text-apple-secondary mb-3">{label}</p>

      {/* Month navigation */}
      <div className="flex items-center justify-between mb-3">
        <button onClick={prevMonth} className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-black/5 text-apple-secondary text-sm">
          &lt;
        </button>
        <span className="text-sm font-semibold text-apple-text">
          {year}년 {month + 1}월
        </span>
        <button onClick={nextMonth} className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-black/5 text-apple-secondary text-sm">
          &gt;
        </button>
      </div>

      {/* Day-of-week header */}
      <div className="grid grid-cols-7 mb-1">
        {DAY_NAMES.map((d) => (
          <div key={d} className="text-center text-[10px] font-medium text-apple-tertiary py-1">{d}</div>
        ))}
      </div>

      {/* Date grid */}
      <div className="grid grid-cols-7">
        {cells.map((day, i) => {
          if (day == null) return <div key={i} />;
          const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
          const selected = dateStr === value;
          const disabled = isDisabled(dateStr);
          const isToday = dateStr === todayStr;

          return (
            <button
              key={i}
              disabled={disabled}
              onClick={() => onChange(dateStr)}
              className={`h-8 w-full text-xs rounded-full transition-all duration-150 ${
                selected
                  ? "bg-apple-blue text-white font-semibold"
                  : disabled
                    ? "text-apple-tertiary/40 cursor-not-allowed"
                    : isToday
                      ? "ring-1 ring-apple-blue text-apple-blue font-medium hover:bg-apple-blue/10"
                      : "text-apple-text hover:bg-black/5"
              }`}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Source filter options ────────────────────────────── */

const SOURCE_OPTIONS = [
  { label: "전체", value: "" },
  ...Object.entries(SOURCE_LABELS).map(([key, { label }]) => ({ label, value: key })),
];

/* ── Search Page ─────────────────────────────────────── */

export default function Search() {
  const [departureDate, setDepartureDate] = useState<string | null>(null);
  const [returnDate, setReturnDate] = useState<string | null>(null);
  const [groups, setGroups] = useState<DestinationGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);
  const [activeDest, setActiveDest] = useState<string | null>(null);
  const [activeTripType, setActiveTripType] = useState<string | undefined>(undefined);
  const [activeSource, setActiveSource] = useState<string>("");

  const handleDepartureChange = (date: string) => {
    setDepartureDate(date);
    if (returnDate && date >= returnDate) {
      setReturnDate(null);
    }
  };

  const handleSearch = () => {
    if (!departureDate || !returnDate) return;
    setLoading(true);
    setError("");
    setSearched(true);
    searchFlights({
      departure_date: departureDate,
      return_date: returnDate,
      trip_type: activeTripType,
      source: activeSource || undefined,
    })
      .then((data) => {
        setGroups(data);
        if (data.length > 0 && (!activeDest || !data.find((g) => g.destination === activeDest))) {
          setActiveDest(data[0].destination);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  // 필터 변경 시 자동 재검색
  useEffect(() => {
    if (searched && departureDate && returnDate && !loading) {
      handleSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTripType, activeSource]);

  const activeGroup = groups.find((g) => g.destination === activeDest) ?? groups[0] ?? null;

  return (
    <div className="space-y-6">
      {/* Calendars */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <CalendarPicker
          label="출발일"
          value={departureDate}
          onChange={handleDepartureChange}
        />
        <CalendarPicker
          label="귀국일"
          value={returnDate}
          onChange={setReturnDate}
          minDate={departureDate ? (() => {
            const d = new Date(departureDate);
            d.setDate(d.getDate() + 1);
            return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
          })() : undefined}
        />
      </div>

      {/* Filters + search button */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={handleSearch}
          disabled={!departureDate || !returnDate || loading}
          className="px-6 py-2 bg-apple-blue text-white rounded-full text-sm font-medium hover:bg-apple-blue-hover disabled:opacity-40 transition-all duration-200"
        >
          {loading ? "검색 중…" : "검색"}
        </button>

        {/* Trip type filter */}
        <div className="flex gap-1.5">
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

        {/* Source dropdown */}
        <select
          value={activeSource}
          onChange={(e) => setActiveSource(e.target.value)}
          className="text-xs px-3 py-1.5 rounded-full bg-white shadow-apple-sm text-apple-text border-none outline-none cursor-pointer"
        >
          {SOURCE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="text-center py-6 text-apple-red text-sm">{error}</div>
      )}

      {/* Results */}
      {!searched && !loading && (
        <div className="flex flex-col items-center py-20 gap-3 text-apple-secondary">
          <p className="text-5xl">&#128197;</p>
          <p className="text-lg font-medium">날짜를 선택하고 검색하세요</p>
          <p className="text-sm">출발일과 귀국일을 지정하면 수집된 항공권을 조회합니다.</p>
        </div>
      )}

      {searched && !loading && groups.length === 0 && !error && (
        <div className="flex flex-col items-center py-20 gap-3 text-apple-secondary">
          <p className="text-5xl">&#9992;</p>
          <p className="text-lg font-medium">해당 날짜의 항공권 데이터가 없습니다.</p>
          <p className="text-sm">다른 날짜를 선택하거나 수집을 실행해주세요.</p>
        </div>
      )}

      {searched && !loading && activeGroup && (
        <>
          {/* Destination tabs */}
          {groups.length > 1 && (
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
          )}

          {/* Active destination header */}
          <div className="flex items-center gap-2">
            <h2 className="text-xl sm:text-2xl font-bold text-apple-text">{activeGroup.destination_name}</h2>
            <span className="text-sm text-apple-secondary">{activeGroup.destination}</span>
            {activeGroup.min_price > 0 && (
              <span className="text-sm font-semibold text-apple-blue whitespace-nowrap">
                최저 {Math.round(activeGroup.min_price).toLocaleString()}원~
              </span>
            )}
          </div>

          {/* Deal cards */}
          {activeGroup.total_count === 0 ? (
            <div className="text-center py-10 text-apple-secondary text-sm">해당 조건의 항공권이 없습니다.</div>
          ) : (
            <>
              <section>
                <h3 className="text-base font-semibold text-apple-text mb-3">검색 결과</h3>
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
                      <DealCard key={i} deal={deal} rank={activeGroup.top_deals.length + i + 1} />
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
