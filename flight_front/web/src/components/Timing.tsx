import { useEffect, useState } from "react";
import { fetchTimingSeasonal, fetchTimingAdvance } from "../api";
import type { SeasonalPoint, AdvancePoint } from "../types";
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

function priceColor(price: number, min: number, max: number): string {
  const ratio = max > min ? (price - min) / (max - min) : 0;
  return `hsl(${120 - ratio * 120}, 65%, 42%)`;
}

function formatPrice(v: number) {
  return `${Math.round(v / 1000)}천`;
}

function SeasonHeatmap({ data }: { data: SeasonalPoint[] }) {
  if (data.length === 0)
    return <p className="text-sm text-apple-secondary py-4">데이터가 없습니다.</p>;

  // pivot: destination_name → { month → min_price }
  const destNames: Record<string, string> = {};
  const pivot: Record<string, Record<string, number>> = {};
  for (const pt of data) {
    destNames[pt.destination] = pt.destination_name;
    if (!pivot[pt.destination]) pivot[pt.destination] = {};
    pivot[pt.destination][pt.month] = pt.min_price;
  }

  const months = [...new Set(data.map((d) => d.month))].sort();
  const destinations = Object.keys(pivot).sort();

  // global min/max for color scale
  const allPrices = data.map((d) => d.min_price);
  const globalMin = Math.min(...allPrices);
  const globalMax = Math.max(...allPrices);

  return (
    <div className="bg-apple-surface border border-apple-tertiary/50 rounded-2xl shadow-apple-sm p-4 sm:p-6 overflow-x-auto">
      <h3 className="text-sm font-semibold text-apple-text mb-4">월별 시즌 최저가</h3>
      <table className="border-collapse text-xs min-w-max">
        <thead>
          <tr>
            <th className="text-left pr-4 pb-2 text-apple-secondary font-medium min-w-[80px]">목적지</th>
            {months.map((m) => (
              <th key={m} className="pb-2 px-1 text-apple-secondary font-medium min-w-[64px]">
                {m.slice(5)}월
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {destinations.map((dest) => (
            <tr key={dest}>
              <td className="pr-4 py-1 text-apple-text font-medium whitespace-nowrap">
                {destNames[dest]}
              </td>
              {months.map((m) => {
                const price = pivot[dest][m];
                if (price == null) {
                  return (
                    <td key={m} className="px-1 py-1">
                      <div className="rounded-lg bg-apple-text/5 h-10 w-16" />
                    </td>
                  );
                }
                return (
                  <td key={m} className="px-1 py-1">
                    <div
                      className="rounded-lg h-10 w-16 flex items-center justify-center"
                      style={{ backgroundColor: priceColor(price, globalMin, globalMax) }}
                      title={`₩${price.toLocaleString()}`}
                    >
                      <span className="text-white font-semibold leading-tight text-center">
                        {formatPrice(price)}
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-apple-secondary mt-3">
        <span className="inline-block w-3 h-3 rounded-sm mr-1 align-middle" style={{ backgroundColor: "hsl(120,65%,42%)" }} />
        저렴
        <span className="inline-block w-3 h-3 rounded-sm ml-3 mr-1 align-middle" style={{ backgroundColor: "hsl(0,65%,42%)" }} />
        비쌈
      </p>
    </div>
  );
}

function AdvanceChart({
  data,
  dest,
  destOptions,
  onDestChange,
}: {
  data: AdvancePoint[];
  dest: string;
  destOptions: { code: string; name: string }[];
  onDestChange: (v: string) => void;
}) {
  const filtered = data.filter((d) => d.destination === dest);
  // sort ascending for chart (far → near)
  const chartData = [...filtered]
    .sort((a, b) => b.days_before - a.days_before)
    .map((d) => ({
      days: d.days_before,
      평균가: d.avg_price,
      최저가: d.min_price,
      obs: d.obs_count,
    }));

  return (
    <div className="bg-apple-surface border border-apple-tertiary/50 rounded-2xl shadow-apple-sm p-4 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
        <h3 className="text-sm font-semibold text-apple-text">예약 시점별 가격</h3>
        <div className="flex items-center gap-2">
          <label className="text-xs text-apple-secondary shrink-0">목적지</label>
          <select
            value={dest}
            onChange={(e) => onDestChange(e.target.value)}
            className="text-sm bg-apple-bg rounded-xl px-3 py-1.5 appearance-none focus:outline-none focus:ring-2 focus:ring-apple-blue/30"
          >
            {destOptions.map((d) => (
              <option key={d.code} value={d.code}>
                {d.name} ({d.code})
              </option>
            ))}
          </select>
        </div>
      </div>

      {chartData.length === 0 ? (
        <p className="text-sm text-apple-secondary py-4">해당 목적지 데이터가 없습니다.</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d2d2d720" />
              <XAxis
                dataKey="days"
                tick={{ fontSize: 11, fill: "#86868b" }}
                label={{ value: "출발까지 남은 일수", position: "insideBottom", offset: -4, fontSize: 11, fill: "#86868b" }}
                height={40}
              />
              <YAxis tickFormatter={formatPrice} tick={{ fontSize: 11, fill: "#86868b" }} width={45} />
              <Tooltip
                formatter={(v, name) => [`₩${Number(v).toLocaleString()}`, String(name)]}
                labelFormatter={(l) => `출발 ${l}일 전`}
                contentStyle={{ borderRadius: 12, border: "none", boxShadow: "0 2px 12px rgba(0,0,0,0.08)" }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="평균가"
                stroke="#0071e3"
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="최저가"
                stroke="#ff9500"
                strokeWidth={2}
                strokeDasharray="4 3"
                dot={{ r: 3 }}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="text-xs text-apple-secondary mt-2">14일 단위 버킷. 관측치 3개 미만 구간은 제외.</p>
        </>
      )}
    </div>
  );
}

export default function Timing() {
  const [seasonal, setSeasonal] = useState<SeasonalPoint[]>([]);
  const [advance, setAdvance] = useState<AdvancePoint[]>([]);
  const [dest, setDest] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [advLoading, setAdvLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    Promise.all([fetchTimingSeasonal(), fetchTimingAdvance()])
      .then(([s, a]) => {
        clearTimeout(timer);
        setSeasonal(s);
        setAdvance(a);
        if (a.length > 0 && !dest) setDest(a[0].destination);
      })
      .catch((e) => {
        clearTimeout(timer);
        setError(e?.name === "AbortError" ? "데이터 로딩 시간이 초과되었습니다. 새로고침 해주세요." : "데이터를 불러오지 못했습니다.");
      })
      .finally(() => setLoading(false));
  }, []);

  const handleDestChange = (newDest: string) => {
    setDest(newDest);
    setAdvLoading(true);
    fetchTimingAdvance(newDest)
      .then(setAdvance)
      .catch(console.error)
      .finally(() => setAdvLoading(false));
  };

  const destOptions = [...new Map(
    advance.map((d) => [d.destination, { code: d.destination, name: d.destination_name }])
  ).values()];

  // also include destinations from seasonal that might not appear in advance
  const seasonalDests = [...new Map(
    seasonal.map((d) => [d.destination, { code: d.destination, name: d.destination_name }])
  ).values()];
  const allDestOptions = [
    ...destOptions,
    ...seasonalDests.filter((s) => !destOptions.find((d) => d.code === s.code)),
  ].sort((a, b) => a.code.localeCompare(b.code));

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
        <h1 className="text-xl sm:text-2xl font-bold text-apple-text">타이밍</h1>
        <p className="text-xs text-apple-secondary">언제 여행가면 저렴한가? 얼마나 미리 예약해야 하나?</p>
      </div>

      {loading ? (
        <p className="text-sm text-apple-secondary py-8">로딩 중…</p>
      ) : error ? (
        <p className="text-sm text-red-500 py-8">{error}</p>
      ) : (
        <>
          <SeasonHeatmap data={seasonal} />

          {advLoading ? (
            <p className="text-sm text-apple-secondary py-4">로딩 중…</p>
          ) : (
            <AdvanceChart
              data={advance}
              dest={dest}
              destOptions={allDestOptions}
              onDestChange={handleDestChange}
            />
          )}
        </>
      )}
    </div>
  );
}
