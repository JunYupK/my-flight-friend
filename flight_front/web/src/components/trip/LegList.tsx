import { useState } from "react";
import type { MergedLegView } from "../../types";
import { timeAgo } from "../../utils";
import LegCard from "./LegCard";

interface Props {
  direction: "out" | "in";
  legs: MergedLegView[];
  selectedKey: string | null;
  highlightKey: string | null;
  showAll: boolean;
  onShowAll: (v: boolean) => void;
  onSelect: (key: string) => void;
}

type SortKey = "price" | "dep";

function newestFresh(legs: MergedLegView[]): string | null {
  let best: string | null = null;
  let bestT = -Infinity;
  for (const l of legs) {
    for (const p of l.prices) {
      if (p.stale) continue;
      const t = new Date(p.observed_at).getTime();
      if (t > bestT) {
        bestT = t;
        best = p.observed_at;
      }
    }
  }
  return best;
}

function sortLegs(legs: MergedLegView[], key: SortKey): MergedLegView[] {
  const copy = [...legs];
  if (key === "dep") {
    copy.sort((a, b) => (a.dep_time ?? "99:99").localeCompare(b.dep_time ?? "99:99"));
  } else {
    copy.sort((a, b) => (a.best_price ?? Infinity) - (b.best_price ?? Infinity));
  }
  return copy;
}

const chip = (on: boolean) =>
  `rounded-full px-2.5 py-1 text-xs ${on ? "bg-apple-blue text-white" : "bg-apple-text/5 text-apple-secondary"}`;

export default function LegList({ direction, legs, selectedKey, highlightKey, showAll, onShowAll, onSelect }: Props) {
  const [sort, setSort] = useState<SortKey>("price");
  const title = direction === "out" ? "출국편" : "귀국편";
  const visible = sortLegs(showAll ? legs : legs.filter((l) => l.in_condition), sort);
  const observed = newestFresh(legs);
  const hidden = legs.length - legs.filter((l) => l.in_condition).length;

  return (
    <section className="min-w-0">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-apple-text">
          {title} · {visible.length}개{observed ? ` · ${timeAgo(observed)} 확인` : ""}
        </h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <button type="button" className={chip(sort === "price")} onClick={() => setSort("price")}>
            가격
          </button>
          <button type="button" className={chip(sort === "dep")} onClick={() => setSort("dep")}>
            출발시각
          </button>
          <button
            type="button"
            aria-pressed={showAll}
            className={chip(showAll)}
            onClick={() => onShowAll(!showAll)}
          >
            조건 밖 포함{hidden > 0 ? ` (${hidden})` : ""}
          </button>
        </div>
      </div>
      {visible.length === 0 ? (
        <p className="rounded-xl bg-apple-surface p-3 text-sm text-apple-secondary">조건에 맞는 편이 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {visible.map((l) => (
            <LegCard
              key={l.flight_key}
              leg={l}
              direction={direction}
              selected={l.flight_key === selectedKey}
              highlighted={l.flight_key === highlightKey}
              onSelect={() => onSelect(l.flight_key)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
