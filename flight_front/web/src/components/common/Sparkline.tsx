import { Area, AreaChart, ReferenceLine, ResponsiveContainer, YAxis } from "recharts";

export default function Sparkline({
  points,
  low,
}: {
  points: { day: string; combo: number | null }[];
  low?: number | null;
}) {
  if (points.filter((p) => p.combo != null).length < 2) return null;
  return (
    <div className="h-8 w-24" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          {low != null && <ReferenceLine y={low} stroke="var(--muted-foreground)" strokeDasharray="2 2" />}
          <Area
            type="monotone"
            dataKey="combo"
            stroke="var(--primary)"
            fill="var(--primary)"
            fillOpacity={0.15}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
