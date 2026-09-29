import type { MergedLegView, NearMissView, Preferences } from "../../types";
import { formatWon } from "../../utils";

interface Props {
  nearMiss: NearMissView;
  legs: { out: MergedLegView[]; in: MergedLegView[] };
  prefs: Preferences;
  onShow: (direction: "out" | "in", key: string) => void;
}

function hhmmToMin(t: string): number {
  return parseInt(t.slice(0, 2), 10) * 60 + parseInt(t.slice(3, 5), 10);
}

function humanMin(m: number): string {
  const h = Math.floor(m / 60);
  const r = m % 60;
  return h > 0 ? `${h}시간${r > 0 ? ` ${r}분` : ""}` : `${r}분`;
}

function reason(code: string, dir: "out" | "in", leg: MergedLegView | undefined, prefs: Preferences): string {
  const label = dir === "out" ? "출국" : "귀국";
  if (!leg) return code;
  if (code === "time_window") {
    const win = dir === "out" ? prefs.out_dep_window : prefs.in_dep_window;
    if (!leg.dep_time || !win) return `${label} 시간대`;
    const dep = hhmmToMin(leg.dep_time);
    if (dep < hhmmToMin(win[0])) return `${label} ${leg.dep_time} (설정보다 ${humanMin(hhmmToMin(win[0]) - dep)} 이름)`;
    return `${label} ${leg.dep_time} (설정보다 ${humanMin(dep - hhmmToMin(win[1]))} 늦음)`;
  }
  if (code === "nonstop") return `경유 ${leg.stops ?? "?"}회`;
  if (code === "airline") return `항공사 ${leg.airline_name ?? leg.airline_iata ?? ""}`;
  if (code === "duration") {
    const d = leg.duration_min ?? 0;
    return `소요 ${Math.floor(d / 60)}시간 ${d % 60}분`;
  }
  return code;
}

export default function NearMissHint({ nearMiss, legs, prefs, onShow }: Props) {
  const dir: "out" | "in" = nearMiss.direction === "out" ? "out" : "in";
  const leg = legs[dir].find((l) => l.flight_key === nearMiss.flight_key);
  const saving = nearMiss.saving ?? 0;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-apple-orange/10 px-3 py-2 text-sm text-apple-text">
      <span className="min-w-0 break-words">
        조건 밖 · {reason(nearMiss.violated, dir, leg, prefs)} ·{" "}
        {saving > 0 ? `조건 내 최저보다 ${formatWon(saving)} 저렴` : "조건 하나만 풀면 선택지가 있음"}
      </span>
      <button
        type="button"
        onClick={() => onShow(dir, nearMiss.flight_key)}
        className="shrink-0 rounded-full bg-apple-orange/20 px-2.5 py-0.5 text-xs font-medium"
      >
        보기
      </button>
    </div>
  );
}
