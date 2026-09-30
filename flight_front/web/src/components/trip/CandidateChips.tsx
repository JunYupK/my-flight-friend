import type { CandidateView, TripView } from "@/types";
import { formatStay, formatWon } from "@/utils";

export default function CandidateChips({
  candidates,
  legs,
  onSelect,
}: {
  candidates: CandidateView[];
  legs: TripView["legs"];
  onSelect: (outKey: string, inKey: string) => void;
}) {
  if (candidates.length < 2) return null;
  const first = candidates[0];
  return (
    <section aria-label="대표 후보">
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {candidates.map((c, i) => {
          const o = legs.out.find((l) => l.flight_key === c.out_flight_key);
          const n = legs.in.find((l) => l.flight_key === c.in_flight_key);
          const dStay = c.stay_min - first.stay_min;
          return (
            <button
              key={`${c.out_flight_key}|${c.in_flight_key}`}
              type="button"
              onClick={() => onSelect(c.out_flight_key, c.in_flight_key)}
              className="shrink-0 rounded-xl border bg-card px-3 py-2 text-left text-card-foreground transition-colors hover:bg-accent/40 focus-visible:outline-2 focus-visible:outline-ring"
            >
              <div className="text-xs font-medium text-primary">
                {i === 0 ? "최저가" : `+${formatWon(c.price - first.price)} · 현지 ${dStay >= 0 ? "+" : ""}${formatStay(dStay)}`}
              </div>
              <div className="font-semibold tabular-nums">{formatWon(c.price)}</div>
              <div className="text-xs tabular-nums text-muted-foreground">
                {o?.dep_time ?? "--:--"} / {n?.dep_time ?? "--:--"} · 현지 {formatStay(c.stay_min)}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
