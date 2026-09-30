import { useEffect, useRef, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import { patchTrip } from "@/api";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { Preferences, TripView } from "@/types";
import ConditionFields from "./ConditionFields";
import { formatWon } from "@/utils";

/** "06:00" → "06", "12:30" → "12:30", 끝 "23:59" → "24" */
function hourText(t: string, end: boolean): string {
  if (end && t === "23:59") return "24";
  return t.endsWith(":00") ? t.slice(0, 2) : t;
}

function windowText(w: [string, string] | null): string | null {
  return w ? `${hourText(w[0], false)}–${hourText(w[1], true)}시` : null;
}

/** 요약 칩 문구: `출발 06–12시 · 직항`, 조건이 없으면 `조건 없음`. */
function prefsSummary(p: Preferences): string {
  const parts: string[] = [];
  const out = windowText(p.out_dep_window);
  const inn = windowText(p.in_dep_window);
  if (out && out === inn) parts.push(`출발 ${out}`);
  else {
    if (out) parts.push(`가는 편 ${out}`);
    if (inn) parts.push(`오는 편 ${inn}`);
  }
  if (p.nonstop_only) parts.push("직항");
  if (p.include_airlines.length > 0) parts.push(`${p.include_airlines.join("·")}만`);
  if (p.exclude_airlines.length > 0) parts.push(`${p.exclude_airlines.join("·")} 제외`);
  if (p.max_price != null) parts.push(`${formatWon(p.max_price)} 이하`);
  if (p.max_duration_min != null) parts.push(`비행 ${p.max_duration_min}분 이내`);
  return parts.length > 0 ? parts.join(" · ") : "조건 없음";
}

interface Props {
  view: TripView;
  onSaved: (view: TripView) => void;
}

export default function ConditionSheet({ view, onSaved }: Props) {
  const tripId = view.trip.id;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Preferences>(view.trip.prefs);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const seq = useRef(0);

  // 다른 trip으로 이동하면 시트를 닫고 진행 중 응답을 무효화
  useEffect(() => {
    setOpen(false);
    setSaving(false);
    setError("");
    return () => {
      seq.current++;
    };
  }, [tripId]);

  function openSheet(v: boolean) {
    if (v) {
      setDraft(view.trip.prefs);
      setError("");
    }
    setOpen(v);
  }

  function save() {
    const mine = ++seq.current;
    setSaving(true);
    setError("");
    patchTrip(tripId, { prefs: draft })
      .then((v) => {
        if (mine !== seq.current || v.trip.id !== tripId) return;
        onSaved(v);
        setOpen(false);
        toast.success("저장했어요");
      })
      .catch((e: unknown) => {
        if (mine === seq.current) setError(e instanceof Error ? e.message : "저장 실패");
      })
      .finally(() => {
        if (mine === seq.current) setSaving(false);
      });
  }

  const summary = prefsSummary(view.trip.prefs);
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="max-w-full justify-start rounded-full"
        title={summary}
        onClick={() => openSheet(true)}
      >
        <SlidersHorizontal />
        <span className="truncate">{summary}</span>
      </Button>
      <Sheet open={open} onOpenChange={openSheet}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>조건</SheetTitle>
            <SheetDescription>조건에 맞는 항공편으로 최선 조합을 골라요.</SheetDescription>
          </SheetHeader>
          <div className="px-4">
            <ConditionFields prefs={draft} onChange={setDraft} />
            {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
          </div>
          <SheetFooter>
            <Button onClick={save} disabled={saving}>
              {saving ? "저장 중…" : "저장"}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </>
  );
}
