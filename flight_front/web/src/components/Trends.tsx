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
  google_flights: "#3b82f6",
  naver_graphql: "#22c55e",
  amadeus: "#f97316",
};

function sourceName(src: string) {
  if (src === "google_flights") return "Google";
  if (src === "naver_graphql") return "Naver";
  return src;
}

function formatPrice(v: number) {
  return `${Math.round(v / 1000)}천`;
}

/** 현재 월 기준 +6개월 목록 */
function getMonthOptions(): string[] {
  const months: string[] = [];
  const now = new Date();
  for (let offset = 0; offset <= 6; offset++) {
    const d = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return months;
}

/** 캘린더 모드: 출발일별 최저가 차트 */
function CalendarChart({ data, month }: { data: PriceHistoryPoint[]; month: string }) {
  if (data.length === 0) return <p className="text-sm text-gray-400 py-4">해당 월 데이터가 없습니다.</p>;

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
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-600 mb-3">출발일별 최저가 ({month})</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={formatPrice} tick={{ fontSize: 11 }} width={50} />
          <Tooltip
            formatter={(v) => [`₩${Number(v).toLocaleString()}`, ""]}
            labelFormatter={(l) => `출발일: ${month}-${l}`}
          />
          <Legend />
          {sources.map((src) => (
            <Line
              key={src}
              type="monotone"
              dataKey={src}
              stroke={SOURCE_COLORS[src] ?? "#6b7280"}
              name={sourceName(src)}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** 타임라인 모드: 수집 시점별 가격 추이 */
function TimelineChart({ data }: { data: PriceHistoryPoint[] }) {
  if (data.length === 0) return <p className="text-sm text-gray-400 py-4">수집 이력이 없습니다.</p>;

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
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-600 mb-3">수집 시점별 가격 변화</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={formatPrice} tick={{ fontSize: 11 }} width={50} />
          <Tooltip
            formatter={(v) => [`₩${Number(v).toLocaleString()}`, ""]}
            labelFormatter={(l) => `수집일: ${l}`}
          />
          <Legend />
          {sources.map((src) => (
            <Line
              key={src}
              type="monotone"
              dataKey={src}
              stroke={SOURCE_COLORS[src] ?? "#6b7280"}
              name={sourceName(src)}
              dot={{ r: 3 }}
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

  // 캘린더 모드 데이터
  const [calData, setCalData] = useState<PriceHistoryPoint[]>([]);
  const [calLoading, setCalLoading] = useState(false);

  // 타임라인 모드 (특정 여정 선택 시)
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

  // 캘린더 데이터 로드
  useEffect(() => {
    if (!dest || !month) return;
    setCalLoading(true);
    setSelectedTrip(null);
    fetchPriceHistory({ destination: dest, mode: "calendar", month })
      .then((res) => setCalData(res.data))
      .catch(console.error)
      .finally(() => setCalLoading(false));
  }, [dest, month]);

  // 타임라인 데이터 로드
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

  // 캘린더 데이터에서 출발일 목록 추출 (타임라인 선택용)
  const departureDates = [...new Set(calData.map((d) => d.departure_date!))].sort();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-bold text-gray-800">가격 추이</h1>
        <p className="text-sm text-gray-400">목적지별 항공권 가격 변화를 추적합니다.</p>
      </div>

      {/* 필터 */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-600">목적지</label>
          <select
            value={dest}
            onChange={(e) => setDest(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
          >
            {airports.map((a) => (
              <option key={a.code} value={a.code}>{a.name} ({a.code})</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-600">출발 월</label>
          <select
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
          >
            {getMonthOptions().map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      </div>

      {/* 캘린더 차트 */}
      {calLoading ? (
        <p className="text-sm text-gray-400 py-4">로딩 중…</p>
      ) : (
        <CalendarChart data={calData} month={month} />
      )}

      {/* 출발일 선택 → 타임라인 */}
      {departureDates.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-600">특정 출발일의 가격 변화 보기</h3>
          <div className="flex flex-wrap gap-2">
            {departureDates.map((d) => (
              <button
                key={d}
                onClick={() => setSelectedTrip({ dep: d, ret: "" })}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                  selectedTrip?.dep === d
                    ? "bg-blue-600 text-white"
                    : "bg-white border border-gray-200 text-gray-600 hover:border-blue-300"
                }`}
              >
                {d.slice(5)}
              </button>
            ))}
          </div>

          {selectedTrip && (
            tlLoading ? (
              <p className="text-sm text-gray-400 py-4">로딩 중…</p>
            ) : (
              <TimelineChart data={tlData} />
            )
          )}
        </div>
      )}
    </div>
  );
}
