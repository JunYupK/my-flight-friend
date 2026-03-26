import React, { useState, useEffect, useMemo } from "react";
import { searchFlights, fetchAirports, fetchCalendarPrices } from "../api";
import type { CalendarPrices } from "../api";
import type { DestinationGroup, Airport } from "../types";
import { DAY_NAMES } from "../utils";
import { DealCard, TRIP_TYPE_OPTIONS, SOURCE_LABELS } from "./DealCard";

/* ── helpers ────────────────────────────────────────────── */
function toDateStr(y: number, m: number, d: number) {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/* ── MonthGrid ──────────────────────────────────────────── */
function MonthGrid({
  year, month, today,
  departureDate, returnDate, hoverDate,
  prices, priceThresholds,
  onDayClick, onDayHover, onDayLeave,
}: {
  year: number; month: number; today: string;
  departureDate: string | null; returnDate: string | null; hoverDate: string | null;
  prices: Record<string, number>;
  priceThresholds: { low: number; high: number };
  onDayClick: (d: string) => void;
  onDayHover: (d: string) => void;
  onDayLeave: () => void;
}) {
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  // range end: actual return date or hover preview (only when hovering after departure)
  const rangeEnd = returnDate || (departureDate && hoverDate && hoverDate > departureDate ? hoverDate : null);

  const priceColor = (price: number) => {
    if (price <= priceThresholds.low) return "text-apple-green";
    if (price >= priceThresholds.high) return "text-apple-orange";
    return "text-apple-secondary";
  };

  return (
    <div>
      <div className="text-sm font-semibold text-apple-text text-center mb-3">
        {year}년 {month + 1}월
      </div>
      <div className="grid grid-cols-7 mb-1">
        {DAY_NAMES.map((d) => (
          <div key={d} className="text-center text-[10px] font-medium text-apple-tertiary py-1">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {cells.map((day, i) => {
          if (day == null) return <div key={i} className="h-12" />;
          const dateStr = toDateStr(year, month + 1, day);
          const isDisabled = dateStr < today;
          const isDeparture = dateStr === departureDate;
          const isReturn = !!returnDate && dateStr === returnDate;
          const isSelected = isDeparture || isReturn;
          const isToday = dateStr === today;

          // range highlight logic
          const rangeActive = !!(departureDate && rangeEnd && departureDate !== rangeEnd);
          const rangeMin = rangeActive ? (departureDate! < rangeEnd! ? departureDate! : rangeEnd!) : null;
          const rangeMax = rangeActive ? (departureDate! < rangeEnd! ? rangeEnd! : departureDate!) : null;
          const inRange = !!(rangeMin && rangeMax && dateStr > rangeMin && dateStr < rangeMax);
          const isRangeStart = rangeActive && dateStr === rangeMin;
          const isRangeEnd = rangeActive && dateStr === rangeMax;

          const price = prices[dateStr];

          return (
            <div key={i} className="relative h-12 flex items-center justify-center">
              {/* Range background strip */}
              {(inRange || isRangeStart || isRangeEnd) && (
                <div
                  className="absolute inset-y-1.5 bg-apple-blue/10 pointer-events-none"
                  style={{
                    left: isRangeStart ? "50%" : 0,
                    right: isRangeEnd ? "50%" : 0,
                  }}
                />
              )}
              {/* Day button */}
              <button
                disabled={isDisabled}
                onClick={() => !isDisabled && onDayClick(dateStr)}
                onMouseEnter={() => !isDisabled && onDayHover(dateStr)}
                onMouseLeave={onDayLeave}
                className={`relative z-10 w-9 h-10 flex flex-col items-center justify-center rounded-full transition-colors duration-100 ${
                  isSelected
                    ? "bg-apple-blue text-white"
                    : isToday
                      ? "ring-1 ring-apple-blue text-apple-blue"
                      : isDisabled
                        ? "text-apple-tertiary/40 cursor-not-allowed"
                        : "text-apple-text hover:bg-black/5"
                }`}
              >
                <span className="text-xs font-medium leading-none">{day}</span>
                {price && !isDisabled && (
                  <span className={`text-[9px] leading-none mt-0.5 ${isSelected ? "text-white/80" : priceColor(price)}`}>
                    {Math.round(price / 1000)}k
                  </span>
                )}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── RangePicker ────────────────────────────────────────── */
function RangePicker({
  departureDate, returnDate, destination,
  onDepartureChange, onReturnChange,
}: {
  departureDate: string | null;
  returnDate: string | null;
  destination: string;
  onDepartureChange: (d: string) => void;
  onReturnChange: (d: string | null) => void;
}) {
  const today = useMemo(() => {
    const d = new Date();
    return toDateStr(d.getFullYear(), d.getMonth() + 1, d.getDate());
  }, []);

  const [viewMonth, setViewMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const [calPrices, setCalPrices] = useState<CalendarPrices>({ out: {}, in: {} });

  const m1y = viewMonth.getFullYear();
  const m1m = viewMonth.getMonth();
  const m2 = new Date(m1y, m1m + 1, 1);
  const m2y = m2.getFullYear();
  const m2m = m2.getMonth();

  useEffect(() => {
    const from = toDateStr(m1y, m1m + 1, 1);
    const to = toDateStr(m2y, m2m + 1, new Date(m2y, m2m + 1, 0).getDate());
    fetchCalendarPrices({ destination, from, to }).then(setCalPrices).catch(() => {});
  }, [destination, m1y, m1m]);

  // Show out_price when selecting departure, in_price when selecting return
  const selectingReturn = !!(departureDate && !returnDate);
  const activePrices = selectingReturn ? calPrices.in : calPrices.out;

  const priceThresholds = useMemo(() => {
    const vals = Object.values(activePrices);
    if (!vals.length) return { low: Infinity, high: 0 };
    const sorted = [...vals].sort((a, b) => a - b);
    return {
      low: sorted[Math.floor(sorted.length * 0.33)],
      high: sorted[Math.floor(sorted.length * 0.67)],
    };
  }, [activePrices]);

  const handleDayClick = (dateStr: string) => {
    if (!departureDate || returnDate) {
      onDepartureChange(dateStr);
      onReturnChange(null);
    } else if (dateStr <= departureDate) {
      onDepartureChange(dateStr);
    } else {
      onReturnChange(dateStr);
    }
  };

  const stayNights = departureDate && returnDate
    ? Math.round((new Date(returnDate).getTime() - new Date(departureDate).getTime()) / 86400000)
    : null;

  const statusText = returnDate && departureDate
    ? `${departureDate} → ${returnDate} (${stayNights}박)`
    : departureDate
      ? "귀국일을 선택하세요"
      : "출발일을 선택하세요";

  const monthGridProps = {
    today,
    departureDate, returnDate, hoverDate,
    prices: activePrices,
    priceThresholds,
    onDayClick: handleDayClick,
    onDayHover: setHoverDate,
    onDayLeave: () => setHoverDate(null),
  };

  return (
    <div className="bg-white rounded-2xl shadow-apple-sm p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-apple-secondary">{statusText}</span>
        <div className="flex gap-1">
          <button
            onClick={() => setViewMonth(new Date(m1y, m1m - 1, 1))}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-black/5 text-apple-secondary text-sm"
          >
            &lt;
          </button>
          <button
            onClick={() => setViewMonth(new Date(m1y, m1m + 1, 1))}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-black/5 text-apple-secondary text-sm"
          >
            &gt;
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 sm:divide-x sm:divide-apple-tertiary/30">
        <MonthGrid year={m1y} month={m1m} {...monthGridProps} />
        <div className="sm:pl-6">
          <MonthGrid year={m2y} month={m2m} {...monthGridProps} />
        </div>
      </div>

      {Object.keys(activePrices).length > 0 && (
        <div className="flex items-center gap-4 mt-4 pt-3 border-t border-apple-tertiary/30 text-[10px] text-apple-secondary">
          <span>{selectingReturn ? "귀국 편 최저가" : "출발 편 최저가"}:</span>
          <span className="text-apple-green font-medium">저렴</span>
          <span>보통</span>
          <span className="text-apple-orange font-medium">비쌈</span>
        </div>
      )}
    </div>
  );
}

/* ── Source filter options ──────────────────────────────── */
const SOURCE_OPTIONS = [
  { label: "전체", value: "" },
  ...Object.entries(SOURCE_LABELS).map(([key, { label }]) => ({ label, value: key })),
];

/* ── Search Page ────────────────────────────────────────── */
export default function Search() {
  const [airports, setAirports] = useState<Airport[]>([]);
  const [destination, setDestination] = useState<string | null>(null);
  const [departureDate, setDepartureDate] = useState<string | null>(null);
  const [returnDate, setReturnDate] = useState<string | null>(null);
  const [groups, setGroups] = useState<DestinationGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);
  const [activeDest, setActiveDest] = useState<string | null>(null);
  const [activeTripType, setActiveTripType] = useState<string | undefined>(undefined);
  const [activeSource, setActiveSource] = useState<string>("");

  useEffect(() => {
    fetchAirports().then(setAirports).catch(() => {});
  }, []);

  const handleDepartureChange = (date: string) => {
    setDepartureDate(date);
    setReturnDate(null);
  };

  const handleDestinationChange = (code: string) => {
    setDestination(code);
    setDepartureDate(null);
    setReturnDate(null);
    setSearched(false);
    setGroups([]);
  };

  const handleSearch = () => {
    if (!destination || !departureDate || !returnDate) return;
    setLoading(true);
    setError("");
    setSearched(true);
    searchFlights({
      departure_date: departureDate,
      return_date: returnDate,
      destination,
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
    if (searched && destination && departureDate && returnDate && !loading) {
      handleSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTripType, activeSource]);

  const activeGroup = groups.find((g) => g.destination === activeDest) ?? groups[0] ?? null;

  return (
    <div className="space-y-6">
      {/* Step 1: 여행지 선택 */}
      <div>
        <p className="text-xs font-medium text-apple-secondary mb-2">여행지</p>
        <div className="flex flex-wrap gap-2">
          {airports.map((a) => (
            <button
              key={a.code}
              onClick={() => handleDestinationChange(a.code)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                destination === a.code
                  ? "bg-apple-text text-white"
                  : "bg-white text-apple-secondary shadow-apple-sm hover:text-apple-text"
              }`}
            >
              {a.name} <span className="text-xs opacity-60">{a.code}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Step 2: 날짜 범위 선택 */}
      {destination && (
        <RangePicker
          departureDate={departureDate}
          returnDate={returnDate}
          destination={destination}
          onDepartureChange={handleDepartureChange}
          onReturnChange={setReturnDate}
        />
      )}

      {/* Step 3: 검색 + 필터 */}
      {destination && departureDate && returnDate && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleSearch}
            disabled={loading}
            className="px-6 py-2 bg-apple-blue text-white rounded-full text-sm font-medium hover:bg-apple-blue-hover disabled:opacity-40 transition-all duration-200"
          >
            {loading ? "검색 중…" : "검색"}
          </button>
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
      )}

      {error && <div className="text-center py-6 text-apple-red text-sm">{error}</div>}

      {/* 초기 안내 */}
      {!destination && (
        <div className="flex flex-col items-center py-20 gap-3 text-apple-secondary">
          <p className="text-5xl">✈️</p>
          <p className="text-lg font-medium">여행지를 선택하세요</p>
          <p className="text-sm">여행지를 고른 뒤 출발일과 귀국일을 지정하세요.</p>
        </div>
      )}

      {destination && !departureDate && (
        <div className="flex flex-col items-center py-10 gap-2 text-apple-secondary">
          <p className="text-sm">캘린더에서 출발일을 선택하세요.</p>
        </div>
      )}

      {searched && !loading && groups.length === 0 && !error && (
        <div className="flex flex-col items-center py-20 gap-3 text-apple-secondary">
          <p className="text-5xl">✈️</p>
          <p className="text-lg font-medium">해당 날짜의 항공권 데이터가 없습니다.</p>
          <p className="text-sm">다른 날짜를 선택하거나 수집을 실행해주세요.</p>
        </div>
      )}

      {searched && !loading && activeGroup && (
        <>
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

          <div className="flex items-center gap-2">
            <h2 className="text-xl sm:text-2xl font-bold text-apple-text">{activeGroup.destination_name}</h2>
            <span className="text-sm text-apple-secondary">{activeGroup.destination}</span>
            {activeGroup.min_price > 0 && (
              <span className="text-sm font-semibold text-apple-blue whitespace-nowrap">
                최저 {Math.round(activeGroup.min_price).toLocaleString()}원~
              </span>
            )}
          </div>

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
