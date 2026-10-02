import { useState } from "react";
import type { ReactElement } from "react";
import { ChevronDown } from "lucide-react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { RunPoint } from "@/types";
import { formatWon, md, mdHm } from "@/utils";

interface Props {
  points: RunPoint[];
  target?: number | null;
}

/** 시각 축에 놓기 위한 epoch ms(`t`)를 붙인 점. */
type ChartPoint = RunPoint & { t: number };

interface DotArgs {
  cx?: number;
  cy?: number;
  payload?: ChartPoint;
}

/** 부분 데이터(일부 제공자 누락) 수집은 속 빈 점. */
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

/** 첫·마지막 수집 사이의 로컬 자정들 (같은 날짜 눈금 중복 방지). */
function dayTicks(first: number, last: number): number[] {
  const d = new Date(first);
  d.setHours(0, 0, 0, 0);
  if (d.getTime() < first) d.setDate(d.getDate() + 1);
  const ticks: number[] = [];
  for (; d.getTime() <= last; d.setDate(d.getDate() + 1)) ticks.push(d.getTime());
  return ticks;
}

function thousands(v: number): string {
  return `${Math.round(v / 1000).toLocaleString("ko-KR")}천`;
}

export default function PriceHistoryChart({ points, target }: Props) {
  const [open, setOpen] = useState(false);
  const data: ChartPoint[] = points.map((p) => ({ ...p, t: Date.parse(p.at) }));
  const priced = data.filter((p) => p.combo != null);
  let low: ChartPoint | null = null;
  for (const p of priced) if (low === null || (p.combo as number) < (low.combo as number)) low = p;
  const hasPartial = priced.some((p) => p.partial);
  const ticks = data.length > 0 ? dayTicks(data[0].t, data[data.length - 1].t) : [];

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
                <LineChart data={data} margin={{ top: 16, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis
                    dataKey="t"
                    type="number"
                    scale="time"
                    domain={["dataMin", "dataMax"]}
                    ticks={ticks}
                    tickFormatter={md}
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
                    labelFormatter={(t) => mdHm(Number(t))}
                    formatter={(v, _n, item) => [
                      `${formatWon(Number(v))}${(item.payload as ChartPoint).partial ? " (일부 제공자 누락)" : ""}`,
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
                    type="linear"
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
                      x={low.t}
                      y={low.combo as number}
                      r={5}
                      fill="var(--primary)"
                      stroke="var(--card)"
                      strokeWidth={2}
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 px-2 text-xs text-muted-foreground">
              수집별 조합 최저가
              {low && ` · 최저 ${formatWon(low.combo as number)} (${mdHm(low.t)})`}
              {hasPartial ? " · 속 빈 점 = 일부 제공자 누락" : ""}
            </p>
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
