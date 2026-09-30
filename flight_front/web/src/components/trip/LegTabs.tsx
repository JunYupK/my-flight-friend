import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { MergedLegView, TripView } from "@/types";
import LegCard from "./LegCard";

type Dir = "out" | "in";

interface Props {
  view: TripView;
  selected: { out?: string; in?: string };
  highlighted: string | null;
  onSelect: (direction: Dir, key: string) => void;
}

function byPrice(legs: MergedLegView[]): MergedLegView[] {
  return [...legs].sort((a, b) => (a.best_price ?? Infinity) - (b.best_price ?? Infinity));
}

/** 강조할 편이 어느 쪽에 있는지와 조건 밖인지. */
function locate(view: TripView, key: string | null): { dir: Dir; outside: boolean } | null {
  if (key === null) return null;
  for (const dir of ["out", "in"] as const) {
    const leg = view.legs[dir].find((l) => l.flight_key === key);
    if (leg) return { dir, outside: !leg.in_condition };
  }
  return null;
}

export default function LegTabs({ view, selected, highlighted, onSelect }: Props) {
  const initial = locate(view, highlighted);
  const [tab, setTab] = useState<Dir>(initial?.dir ?? "out");
  const [outsideOpen, setOutsideOpen] = useState<Record<Dir, boolean>>({
    out: initial?.dir === "out" && initial.outside,
    in: initial?.dir === "in" && initial.outside,
  });
  const [prevHighlighted, setPrevHighlighted] = useState(highlighted);

  // 새 강조 요청이 오면 렌더 중에 탭·"조건 밖"을 맞춰, 커밋 시점에 해당 카드가 DOM에 있게 한다
  if (highlighted !== prevHighlighted) {
    setPrevHighlighted(highlighted);
    const at = locate(view, highlighted);
    if (at) {
      setTab(at.dir);
      if (at.outside) setOutsideOpen((s) => ({ ...s, [at.dir]: true }));
    }
  }

  const split = (dir: Dir) => {
    const legs = view.legs[dir];
    return {
      inside: byPrice(legs.filter((l) => l.in_condition)),
      outside: byPrice(legs.filter((l) => !l.in_condition)),
    };
  };
  const lists = { out: split("out"), in: split("in") };

  const renderCards = (dir: Dir, legs: MergedLegView[]) => (
    <ul className="space-y-3">
      {legs.map((l) => (
        <LegCard
          key={l.flight_key}
          leg={l}
          direction={dir}
          selected={selected[dir] === l.flight_key}
          highlighted={highlighted === l.flight_key}
          onSelect={() => onSelect(dir, l.flight_key)}
        />
      ))}
    </ul>
  );

  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as Dir)} className="gap-3">
      <TabsList className="w-full sm:w-fit">
        <TabsTrigger value="out" className="px-4">
          가는 편 ({lists.out.inside.length})
        </TabsTrigger>
        <TabsTrigger value="in" className="px-4">
          오는 편 ({lists.in.inside.length})
        </TabsTrigger>
      </TabsList>
      {(["out", "in"] as const).map((dir) => {
        const { inside, outside } = lists[dir];
        return (
          <TabsContent key={dir} value={dir} className="space-y-3">
            {inside.length > 0 ? (
              renderCards(dir, inside)
            ) : (
              <p className="rounded-2xl border border-dashed p-4 text-center text-sm text-muted-foreground">
                {outside.length > 0 ? "조건에 맞는 편이 없어요." : "항공편이 없어요."}
              </p>
            )}
            {outside.length > 0 && (
              <Collapsible
                open={outsideOpen[dir]}
                onOpenChange={(v) => setOutsideOpen((s) => ({ ...s, [dir]: v }))}
              >
                <CollapsibleTrigger className="flex items-center gap-1 py-1 text-sm text-muted-foreground hover:text-foreground">
                  조건 밖 {outside.length}개
                  <ChevronDown className={`size-4 transition-transform ${outsideOpen[dir] ? "rotate-180" : ""}`} />
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-2">{renderCards(dir, outside)}</CollapsibleContent>
              </Collapsible>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}
