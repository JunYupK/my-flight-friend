import { Lightbulb } from "lucide-react";
import type { MergedLegView, NearMissView, TripView } from "@/types";
import { formatWon } from "@/utils";

/** 위반 코드 → "…을 풀면" 앞부분 설명 (leg를 알면 구체적으로). */
function describe(code: string, dir: "out" | "in", leg: MergedLegView | undefined): string {
  const label = dir === "out" ? "출국" : "귀국";
  if (code === "time_window") return leg?.dep_time ? `${label} 출발 시간을 ${leg.dep_time}까지 늘리` : `${label} 시간대를 넓히`;
  if (code === "nonstop") return leg?.stops != null ? `경유 ${leg.stops}회를 허용하` : "직항 조건을 풀";
  if (code === "airline") return `항공사 제한(${leg?.airline_name ?? leg?.airline_iata ?? "다른 항공사"})을 풀`;
  if (code === "duration") return "소요 시간 제한을 풀";
  return `${code} 조건을 풀`;
}

export default function NearMissLine({
  nearMiss,
  legs,
  onJump,
}: {
  nearMiss: NearMissView | null;
  legs: TripView["legs"];
  onJump: (direction: "out" | "in", key: string) => void;
}) {
  if (!nearMiss) return null;
  const dir: "out" | "in" = nearMiss.direction === "out" ? "out" : "in";
  const leg = legs[dir].find((l) => l.flight_key === nearMiss.flight_key);
  const saving = nearMiss.saving ?? 0;
  const text =
    saving > 0
      ? `${describe(nearMiss.violated, dir, leg)}면 ${formatWon(saving)} 쌈 →`
      : `${describe(nearMiss.violated, dir, leg)}면 선택지가 늘어요 →`;
  return (
    <button
      type="button"
      onClick={() => onJump(dir, nearMiss.flight_key)}
      className="flex w-full items-center gap-2 rounded-xl bg-amber-500/10 px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-amber-500/15 focus-visible:outline-2 focus-visible:outline-ring"
    >
      <Lightbulb className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
      <span className="min-w-0 break-words">{text}</span>
    </button>
  );
}
