import { useEffect, useState } from "react";
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
import { fetchPriceHistory } from "../api";
import type { PriceHistoryPoint } from "../types";

const SOURCE_COLORS: Record<string, string> = {
  google_flights: "#3b82f6",
  naver: "#22c55e",
  amadeus: "#f97316",
};

function formatPrice(v: number) {
  return `${Math.round(v / 1000)}천`;
}

interface PriceChartProps {
  destination: string;
  month: string;
}

export default function PriceChart({ destination, month }: PriceChartProps) {
  const [data, setData] = useState<PriceHistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    fetchPriceHistory({ destination, mode: "calendar", month })
      .then((res) => setData(res.data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [destination, month]);

  if (loading)
    return <p className="text-sm text-gray-400 py-4">차트 로딩 중…</p>;
  if (error)
    return <p className="text-sm text-red-500 py-4">{error}</p>;
  if (data.length === 0)
    return <p className="text-sm text-gray-400 py-4">데이터가 아직 없습니다</p>;

  // pivot: departure_date → { date, google_flights, naver_graphql, amadeus }
  const sources = [...new Set(data.map((d) => d.source))];
  const byDate: Record<string, Record<string, number | string>> = {};
  for (const pt of data) {
    const key = pt.departure_date!;
    if (!byDate[key]) byDate[key] = { date: key.slice(5) }; // MM-DD
    byDate[key][pt.source] = pt.min_price;
  }
  const chartData = Object.values(byDate).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <ResponsiveContainer width="100%" height={260}>
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
              name={src === "google_flights" ? "Google" : src === "naver" ? "Naver" : src}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
