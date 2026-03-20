import { useEffect, useState } from "react";
import { fetchAirports, fetchPriceHistory } from "../api";
import type { Airport, PriceHistoryPoint } from "../types";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const SOURCE_COLORS: Record<string, string> = {
  google_flights: "#0071e3",
  naver_graphql: "#34c759",
  amadeus: "#ff9500",
};

function sourceName(src: string) {
  if (src === "google_flights") return "Google";
  if (src === "naver_graphql") return "Naver";
  return src;
}

function formatPrice(v: number) {
  return `${Math.round(v / 1000)}천`;
}

function getMonthOptions(): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let offset = 0; offset <= 6; offset++) {
    const d = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return months;
}

function CalendarChart({ data, month }: { data: PriceHistoryPoint[]; month: string }) {
  if (data.length === 0) return <p className="text-sm text-apple-secondary py-4">해당 월 데이터가 없습니다.</p>;

  const sources = [...new Set(data.map((d) => d.source))];
  const byDate: Record<string, Record<string, number | string>> = {};
  for (const pt of data) {
    const key = pt.departure_date!;
    if (!byDate[key]) byDate[key] = { date: key.slice(5) };
    byDate[key][pt.source] = pt.min_price;
  }
  const chartData = Object.values(byDate).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );

  return (
    <div className="bg-white rounded-2xl shadow-apple-sm p-4 sm:p-6">
      <h3 className="text-sm font-semibold text-apple-text mb-4">출발일별 최저가 ({month})</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#d2d2d720" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#86868b" }} />
          <YAxis tickFormatter={formatPrice} tick={{ fontSize: 11, fill: "#86868b" }} width={45} />
          <Tooltip
            formatter={(v) => [`₩${Number(v).toLocaleString()}`, ""]}
            labelFormatter={(l) => `출발일: ${month}-${l}`}
            contentStyle={{ borderRadius: 12, border: "none", boxShadow: "0 2px 12px rgba(0,0,0,0.08)" }}
          />
          <Legend />
          {sources.map((src) => (
            <Line
              key={src}
              type="monotone"
              dataKey={src}
              stroke={SOURCE_COLORS[src] ?? "#86868b"}
              name={sourceName(src)}
              dot={{ r: 3 }}
              strokeWidth={2}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TimelineChart({ data }: { data: PriceHistoryPoint[] }) {
  if (data.length === 0) return <p className="text-sm text-apple-secondary py-4">수집 이력이 없습니다.</p>;

  const sources = [...new Set(data.map((d) => d.source))];
  const byDate: Record<string, Record<string, number | string>> = {};
  for (const pt of data) {
    const key = pt.check_date!;
    if (!byDate[key]) byDate[key] = { date: key.slice(5) };
    byDate[key][pt.source] = pt.min_price;
  }
  const chartData = Object.values(byDate).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );

  return (
    <div className="bg-white rounded-2xl shadow-apple-sm p-4 sm:p-6">
      <h3 className="text-sm font-semibold text-apple-text mb-4">수집 시점별 가격 변화</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#d2d2d720" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#86868b" }} />
          <YAxis tickFormatter={formatPrice} tick={{ fontSize: 11, fill: "#86868b" }} width={45} />
          <Tooltip
            formatter={(v) => [`₩${Number(v).toLocaleString()}`, ""]}
            labelFormatter={(l) => `수집일: ${l}`}
            contentStyle={{ borderRadius: 12, border: "none", boxShadow: "0 2px 12px rgba(0,0,0,0.08)" }}
          />
          <Legend />
          {sources.map((src) => (
            <Line
              key={src}
              type="monotone"
              dataKey={src}
              stroke={SOURCE_COLORS[src] ?? "#86868b"}
              name={sourceName(src)}
              dot={{ r: 3 }}
              strokeWidth={2}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Trends() {
  const [airports, setAirports] = useState<Airport[]>([]);
  const [dest, setDest] = useState("");
  const [month, setMonth] = useState(() => getMonthOptions()[0]);

  const [calData, setCalData] = useState<PriceHistoryPoint[]>([]);
  const [calLoading, setCalLoading] = useState(false);

  const [selectedTrip, setSelectedTrip] = useState<{ dep: string; ret: string } | null>(null);
  const [tlData, setTlData] = useState<PriceHistoryPoint[]>([]);
  const [tlLoading, setTlLoading] = useState(false);

  useEffect(() => {
    fetchAirports()
      .then((list) => {
        setAirports(list);
        if (list.length > 0) setDest(list[0].code);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!dest || !month) return;
    setCalLoading(true);
    setSelectedTrip(null);
    fetchPriceHistory({ destination: dest, mode: "calendar", month })
      .then((res) => setCalData(res.data))
      .catch(console.error)
      .finally(() => setCalLoading(false));
  }, [dest, month]);

  useEffect(() => {
    if (!dest || !selectedTrip) return;
    setTlLoading(true);
    fetchPriceHistory({
      destination: dest,
      mode: "timeline",
      departure_date: selectedTrip.dep,
      return_date: selectedTrip.ret,
    })
      .then((res) => setTlData(res.data))
      .catch(console.error)
      .finally(() => setTlLoading(false));
  }, [dest, selectedTrip]);

  const departureDates = [...new Set(calData.map((d) => d.departure_date!))].sort();

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <h1 className="text-xl sm:text-2xl font-bold text-apple-text">가격 추이</h1>
        <p className="text-xs text-apple-secondary">목적지별 항공권 가격 변화를 추적합니다.</p>
      </div>

      {/* 필터 */}
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-apple-secondary shrink-0">목적지</label>
          <select
            value={dest}
            onChange={(e) => setDest(e.target.value)}
            className="text-sm bg-white rounded-xl px-3 py-2 shadow-apple-sm appearance-none focus:outline-none focus:ring-2 focus:ring-apple-blue/30 min-w-0"
          >
            {airports.map((a) => (
              <option key={a.code} value={a.code}>{a.name} ({a.code})</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-apple-secondary shrink-0">출발 월</label>
          <select
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="text-sm bg-white rounded-xl px-3 py-2 shadow-apple-sm appearance-none focus:outline-none focus:ring-2 focus:ring-apple-blue/30 min-w-0"
          >
            {getMonthOptions().map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      </div>

      {/* 캘린더 차트 */}
      {calLoading ? (
        <p className="text-sm text-apple-secondary py-4">로딩 중…</p>
      ) : (
        <CalendarChart data={calData} month={month} />
      )}

      {/* 출발일 선택 → 타임라인 */}
      {departureDates.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-apple-text">특정 출발일의 가격 변화 보기</h3>
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
            <div className="flex gap-1.5 w-max sm:w-auto sm:flex-wrap">
              {departureDates.map((d) => (
                <button
                  key={d}
                  onClick={() => setSelectedTrip({ dep: d, ret: "" })}
                  className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all duration-200 whitespace-nowrap ${
                    selectedTrip?.dep === d
                      ? "bg-apple-text text-white"
                      : "bg-white text-apple-secondary shadow-apple-sm hover:text-apple-text"
                  }`}
                >
                  {d.slice(5)}
                </button>
              ))}
            </div>
          </div>

          {selectedTrip && (
            tlLoading ? (
              <p className="text-sm text-apple-secondary py-4">로딩 중…</p>
            ) : (
              <TimelineChart data={tlData} />
            )
          )}
        </div>
      )}
    </div>
  );
}
