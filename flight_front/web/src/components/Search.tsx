import { useState, useEffect } from "react";
import { searchFlights, fetchAirports } from "../api";
import type { DestinationGroup, Airport } from "../types";
import { DealCard, TRIP_TYPE_OPTIONS, SOURCE_LABELS } from "./DealCard";
import RangePicker from "./Calendar";

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
                  ? "bg-apple-text text-apple-bg"
                  : "bg-apple-surface text-apple-secondary shadow-apple-sm hover:text-apple-text"
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
            className="px-6 py-2 bg-apple-blue text-apple-bg rounded-full text-sm font-medium hover:bg-apple-blue-hover disabled:opacity-40 transition-all duration-200"
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
                    ? "bg-apple-text text-apple-bg"
                    : "bg-apple-surface text-apple-secondary shadow-apple-sm hover:text-apple-text"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <select
            value={activeSource}
            onChange={(e) => setActiveSource(e.target.value)}
            className="text-xs px-3 py-1.5 rounded-full bg-apple-surface shadow-apple-sm text-apple-text border-none outline-none cursor-pointer"
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
                          ? "bg-apple-text text-apple-bg shadow-apple"
                          : "bg-apple-surface text-apple-text shadow-apple-sm hover:shadow-apple"
                      }`}
                    >
                      <span className="text-sm font-semibold">{g.destination_name}</span>
                      <span className={`text-[11px] ${isActive ? "text-apple-bg/60" : "text-apple-secondary"}`}>
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
