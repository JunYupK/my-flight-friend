import { useState } from "react";
import type { ReactElement } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { getHistory } from "../../api";
import type { DayPoint } from "../../types";

type Key = "combo" | "out_min" | "in_min";

const SERIES: { key: Key; name: string; color: string }[] = [
  { key: "combo", name: "조합", color: "#3b82f6" },
  { key: "out_min", name: "출국", color: "#22c55e" },
  { key: "in_min", name: "귀국", color: "#f97316" },
];

function formatPrice(v: number) {
  return `${Math.round(v / 1000)}천`;
}

interface DotArgs {
  cx?: number;
  cy?: number;
  payload?: DayPoint;
  stroke?: string;
}

function makeDot(color: string) {
  return function PartialDot({ cx, cy, payload }: DotArgs): ReactElement {
    if (cx == null || cy == null) return <g />;
    const hollow = payload?.partial === true;
    return <circle cx={cx} cy={cy} r={3} stroke={color} strokeWidth={2} fill={hollow ? "#ffffff" : color} />;
  };
}

export default function HistoryChart({ tripId }: { tripId: number }) {
  const [data, setData] = useState<DayPoint[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [shown, setShown] = useState<Record<Key, boolean>>({ combo: true, out_min: true, in_min: true });

  function onToggle(open: boolean) {
    if (!open || data !== null || loading) return;
    setLoading(true);
    setError("");
    getHistory(tripId)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "불러오기 실패"))
      .finally(() => setLoading(false));
  }

  return (
    <details
      className="rounded-2xl bg-apple-surface p-4"
      onToggle={(e) => onToggle(e.currentTarget.open)}
    >
      <summary className="cursor-pointer text-sm font-medium text-apple-text">가격 추이</summary>
      <div className="mt-3">
        {loading && <p className="text-sm text-apple-secondary">차트 로딩 중…</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
        {data && data.length === 0 && <p className="text-sm text-apple-secondary">데이터가 아직 없습니다</p>}
        {data && data.length > 0 && (
          <>
            <div className="mb-2 flex flex-wrap gap-3 text-sm">
              {SERIES.map((s) => (
                <label key={s.key} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={shown[s.key]}
                    onChange={() => setShown({ ...shown, [s.key]: !shown[s.key] })}
                  />
                  <span style={{ color: s.color }}>{s.name}</span>
                </label>
              ))}
              <span className="text-xs text-apple-secondary">속 빈 점 = 일부 제공자 누락</span>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="day" tickFormatter={(d: string) => d.slice(5)} tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={formatPrice} tick={{ fontSize: 11 }} width={45} domain={["auto", "auto"]} />
                <Tooltip formatter={(v) => [`${Number(v).toLocaleString("ko-KR")}원`, ""]} />
                <Legend />
                {SERIES.filter((s) => shown[s.key]).map((s) => (
                  <Line
                    key={s.key}
                    type="monotone"
                    dataKey={s.key}
                    name={s.name}
                    stroke={s.color}
                    dot={makeDot(s.color)}
                    connectNulls
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </div>
    </details>
  );
}
