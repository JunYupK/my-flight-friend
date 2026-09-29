import type { CandidateView, MergedLegView } from "../../types";
import { formatStay, formatWon } from "../../utils";

interface Props {
  candidates: CandidateView[];
  legs: { out: MergedLegView[]; in: MergedLegView[] };
  selOut: string | null;
  selIn: string | null;
  onPick: (c: CandidateView) => void;
}

export default function Candidates({ candidates, legs, selOut, selIn, onPick }: Props) {
  if (candidates.length === 0) return null;
  const first = candidates[0];
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium text-apple-text">대표 후보</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {candidates.map((c, i) => {
          const o = legs.out.find((l) => l.flight_key === c.out_flight_key);
          const n = legs.in.find((l) => l.flight_key === c.in_flight_key);
          const active = c.out_flight_key === selOut && c.in_flight_key === selIn;
          return (
            <button
              key={`${c.out_flight_key}|${c.in_flight_key}`}
              type="button"
              onClick={() => onPick(c)}
              className={`min-w-0 rounded-xl bg-apple-surface p-3 text-left ${active ? "ring-2 ring-apple-blue" : "ring-1 ring-apple-text/10"}`}
            >
              <div className="text-xs font-medium text-apple-blue">
                {i === 0
                  ? "최저가"
                  : `+${formatWon(c.price - first.price)} → 현지 +${formatStay(c.stay_min - first.stay_min)}`}
              </div>
              <div className="mt-0.5 text-base font-semibold text-apple-text">{formatWon(c.price)}</div>
              <div className="mt-0.5 text-xs text-apple-secondary">
                {o?.dep_time ?? "--:--"} / {n?.dep_time ?? "--:--"} · 현지 {formatStay(c.stay_min)}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
