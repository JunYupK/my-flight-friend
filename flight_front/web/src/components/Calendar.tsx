import { useState, useEffect, useMemo } from "react";
import { fetchCalendarPrices } from "../api";
import type { CalendarPrices } from "../api";
import { DAY_NAMES } from "../utils";

/* ── helpers ────────────────────────────────────────────── */
function toDateStr(y: number, m: number, d: number) {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/* ── 가격 히트맵 레벨 (분위수 기반 5단계) ─────────────────── */
export function quantileThresholds(prices: number[]): number[] {
  if (!prices.length) return [];
  const sorted = [...prices].sort((a, b) => a - b);
  const q = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))];
  return [q(0.2), q(0.4), q(0.6), q(0.8)];
}

export function priceLevel(price: number, thresholds: number[]): 0 | 1 | 2 | 3 | 4 {
  if (thresholds.length < 4) return 2;
  if (price <= thresholds[0]) return 0;
  if (price <= thresholds[1]) return 1;
  if (price <= thresholds[2]) return 2;
  if (price <= thresholds[3]) return 3;
  return 4;
}

const LEVEL_BG = ["bg-apple-green/20", "bg-apple-green/10", "", "bg-apple-orange/10", "bg-apple-red/15"];
const LEVEL_TEXT = ["text-apple-green", "text-apple-green", "text-apple-secondary", "text-apple-orange", "text-apple-red"];

const LEGEND = [
  { label: "최저", chip: "bg-apple-green/40" },
  { label: "저렴", chip: "bg-apple-green/20" },
  { label: "보통", chip: "bg-apple-tertiary/40" },
  { label: "비쌈", chip: "bg-apple-orange/30" },
  { label: "최고", chip: "bg-apple-red/30" },
];

/* ── MonthGrid ──────────────────────────────────────────── */
function MonthGrid({
  year, month, today,
  departureDate, returnDate, hoverDate,
  prices, thresholds,
  onDayClick, onDayHover, onDayLeave,
}: {
  year: number; month: number; today: string;
  departureDate: string | null; returnDate: string | null; hoverDate: string | null;
  prices: Record<string, number>;
  thresholds: number[];
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
          const level = price != null ? priceLevel(price, thresholds) : null;
          // 히트맵 배경은 선택/오늘/비활성 상태가 아닐 때만
          const heatBg = !isSelected && !isToday && !isDisabled && level != null ? LEVEL_BG[level] : "";
          const heatText = level != null ? LEVEL_TEXT[level] : "text-apple-secondary";

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
                    ? "bg-apple-blue text-apple-bg"
                    : isToday
                      ? "ring-1 ring-apple-blue text-apple-blue"
                      : isDisabled
                        ? "text-apple-tertiary/40 cursor-not-allowed"
                        : `text-apple-text hover:bg-apple-text/5 ${heatBg}`
                }`}
              >
                <span className="text-xs font-medium leading-none">{day}</span>
                {price && !isDisabled && (
                  <span className={`text-[9px] leading-none mt-0.5 ${isSelected ? "text-apple-bg/80" : heatText}`}>
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
export default function RangePicker({
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destination, m1y, m1m]);

  // Show out_price when selecting departure, in_price when selecting return
  const selectingReturn = !!(departureDate && !returnDate);
  const activePrices = selectingReturn ? calPrices.in : calPrices.out;

  const thresholds = useMemo(
    () => quantileThresholds(Object.values(activePrices)),
    [activePrices],
  );

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
    thresholds,
    onDayClick: handleDayClick,
    onDayHover: setHoverDate,
    onDayLeave: () => setHoverDate(null),
  };

  return (
    <div className="bg-apple-surface border border-apple-tertiary/50 rounded-2xl shadow-apple-sm p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-apple-secondary">{statusText}</span>
        <div className="flex gap-1">
          <button
            onClick={() => setViewMonth(new Date(m1y, m1m - 1, 1))}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-apple-text/5 text-apple-secondary text-sm"
          >
            &lt;
          </button>
          <button
            onClick={() => setViewMonth(new Date(m1y, m1m + 1, 1))}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-apple-text/5 text-apple-secondary text-sm"
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
        <div className="flex flex-wrap items-center gap-3 mt-4 pt-3 border-t border-apple-tertiary/30 text-[10px] text-apple-secondary">
          <span>{selectingReturn ? "귀국 편 최저가" : "출발 편 최저가"}:</span>
          {LEGEND.map((l) => (
            <span key={l.label} className="flex items-center gap-1">
              <span className={`inline-block w-3 h-3 rounded-sm ${l.chip}`} />
              {l.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
