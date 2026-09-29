import { useEffect, useState } from "react";
import type { CandidateView, TripView } from "../../types";
import Candidates from "./Candidates";
import FilterBar from "./FilterBar";
import { legDomId } from "./LegCard";
import LegList from "./LegList";
import NearMissHint from "./NearMissHint";

interface Props {
  view: TripView;
  selOut: string | null;
  selIn: string | null;
  onSelectOut: (key: string) => void;
  onSelectIn: (key: string) => void;
  onPick: (c: CandidateView) => void;
  onApplied: (v: TripView) => void;
}

type Dir = "out" | "in";

export default function Results({ view, selOut, selIn, onSelectOut, onSelectIn, onPick, onApplied }: Props) {
  const [tab, setTab] = useState<Dir>("out");
  const [showAll, setShowAll] = useState<Record<Dir, boolean>>({ out: false, in: false });
  const [highlight, setHighlight] = useState<{ dir: Dir; key: string } | null>(null);

  function showLeg(dir: Dir, key: string) {
    setShowAll((s) => ({ ...s, [dir]: true }));
    setTab(dir);
    setHighlight({ dir, key });
  }

  // 목록이 그려진 뒤 해당 편으로 스크롤, 잠시 뒤 강조 해제
  useEffect(() => {
    if (!highlight) return;
    const el = document.getElementById(legDomId(highlight.dir, highlight.key));
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    const t = window.setTimeout(() => setHighlight(null), 3000);
    return () => window.clearTimeout(t);
  }, [highlight]);

  const tabCls = (on: boolean) =>
    `flex-1 rounded-full py-1.5 text-sm font-medium ${on ? "bg-apple-blue text-white" : "bg-apple-text/5 text-apple-secondary"}`;

  return (
    <div className="space-y-4">
      <FilterBar
        tripId={view.trip.id}
        prefs={view.trip.prefs}
        legs={view.legs}
        onApplied={onApplied}
      />
      <Candidates candidates={view.candidates} legs={view.legs} selOut={selOut} selIn={selIn} onPick={onPick} />
      {view.near_miss && (
        <NearMissHint nearMiss={view.near_miss} legs={view.legs} prefs={view.trip.prefs} onShow={showLeg} />
      )}
      <div className="flex gap-2 sm:hidden" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "out"} className={tabCls(tab === "out")} onClick={() => setTab("out")}>
          출국
        </button>
        <button type="button" role="tab" aria-selected={tab === "in"} className={tabCls(tab === "in")} onClick={() => setTab("in")}>
          귀국
        </button>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className={tab === "out" ? "" : "hidden sm:block"}>
          <LegList
            direction="out"
            legs={view.legs.out}
            selectedKey={selOut}
            highlightKey={highlight?.dir === "out" ? highlight.key : null}
            showAll={showAll.out}
            onShowAll={(v) => setShowAll((s) => ({ ...s, out: v }))}
            onSelect={onSelectOut}
          />
        </div>
        <div className={tab === "in" ? "" : "hidden sm:block"}>
          <LegList
            direction="in"
            legs={view.legs.in}
            selectedKey={selIn}
            highlightKey={highlight?.dir === "in" ? highlight.key : null}
            showAll={showAll.in}
            onShowAll={(v) => setShowAll((s) => ({ ...s, in: v }))}
            onSelect={onSelectIn}
          />
        </div>
      </div>
    </div>
  );
}
