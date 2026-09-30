import { useState } from "react";
import type { ReactElement } from "react";
import { ChevronDown } from "lucide-react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { DayPoint } from "@/types";
import { formatWon, shortMd } from "@/utils";

interface Props {
  points: DayPoint[];
  target?: number | null;
}

interface DotArgs {
  cx?: number;
  cy?: number;
  payload?: DayPoint;
}

/** 부분 데이터(일부 제공자 누락) 날은 속 빈 점. */
function PartialDot({ cx, cy, payload }: DotArgs): ReactElement {
  if (cx == null || cy == null || payload?.combo == null) return <g />;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={payload.partial ? 4 : 2.5}
      stroke="var(--primary)"
      strokeWidth={2}
      fill={payload.partial ? "var(--card)" : "var(--primary)"}
    />
  );
}

function thousands(v: number): string {
  return `${Math.round(v / 1000).toLocaleString("ko-KR")}천`;
}

export default function PriceHistoryChart({ points, target }: Props) {
  const [open, setOpen] = useState(false);
  const priced = points.filter((p) => p.combo != null);
  let low: DayPoint | null = null;
  for (const p of priced) if (low === null || (p.combo as number) < (low.combo as number)) low = p;
  const hasPartial = priced.some((p) => p.partial);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-2xl border bg-card text-card-foreground">
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-4 py-3 text-sm font-medium">
        가격 추이
        <ChevronDown className={`size-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-2 pb-4 sm:px-4">
        {priced.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">아직 추이 데이터가 없어요.</p>
        ) : (
          <>
            <div className="h-60 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={points} margin={{ top: 16, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis
                    dataKey="day"
                    tickFormatter={shortMd}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={16}
                  />
                  <YAxis
                    tickFormatter={thousands}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    axisLine={false}
                    tickLine={false}
                    width={52}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
                    contentStyle={{
                      background: "var(--popover)",
                      color: "var(--popover-foreground)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    itemStyle={{ color: "var(--popover-foreground)" }}
                    labelFormatter={(d) => shortMd(String(d))}
                    formatter={(v, _n, item) => [
                      `${formatWon(Number(v))}${(item.payload as DayPoint).partial ? " (일부 제공자 누락)" : ""}`,
                      "조합 최저",
                    ]}
                  />
                  {target != null && (
                    <ReferenceLine
                      y={target}
                      stroke="var(--muted-foreground)"
                      strokeDasharray="4 4"
                      ifOverflow="extendDomain"
                      label={{ value: `목표 ${thousands(target)}`, position: "insideTopRight", fontSize: 11, fill: "var(--muted-foreground)" }}
                    />
                  )}
                  <Line
                    type="monotone"
                    dataKey="combo"
                    stroke="var(--primary)"
                    strokeWidth={2}
                    dot={PartialDot}
                    activeDot={{ r: 5 }}
                    connectNulls
                    isAnimationActive={false}
                  />
                  {low && (
                    <ReferenceDot
                      x={low.day}
                      y={low.combo as number}
                      r={5}
                      fill="var(--primary)"
                      stroke="var(--card)"
                      strokeWidth={2}
                      label={{ value: `최저 ${thousands(low.combo as number)}`, position: "top", fontSize: 11, fill: "var(--foreground)" }}
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 px-2 text-xs text-muted-foreground">
              일별 조합 최저가{hasPartial ? " · 속 빈 점 = 일부 제공자 누락" : ""}
            </p>
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
