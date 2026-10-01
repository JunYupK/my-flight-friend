import { useState } from "react";
import { ChevronDown } from "lucide-react";
import AirlineChips from "@/components/inputs/AirlineChips";
import TimeWindowSlider from "@/components/inputs/TimeWindowSlider";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Preferences } from "@/types";

function numOrNull(s: string): number | null {
  if (s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
}

export default function ConditionFields({
  prefs,
  onChange,
}: {
  prefs: Preferences;
  onChange: (p: Preferences) => void;
}) {
  const [open, setOpen] = useState(false);
  const set = (patch: Partial<Preferences>) => onChange({ ...prefs, ...patch });

  return (
    <div className="space-y-5">
      <TimeWindowSlider label="가는 편 출발 시간" value={prefs.out_dep_window} onChange={(v) => set({ out_dep_window: v })} />
      <TimeWindowSlider label="오는 편 출발 시간" value={prefs.in_dep_window} onChange={(v) => set({ in_dep_window: v })} />
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="cf-nonstop" className="text-sm font-medium">
          직항만
        </Label>
        <Switch id="cf-nonstop" checked={prefs.nonstop_only} onCheckedChange={(v) => set({ nonstop_only: v })} />
      </div>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          상세 조건
          <ChevronDown className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-4 pt-4">
          <AirlineChips label="포함 항공사" value={prefs.include_airlines} onChange={(v) => set({ include_airlines: v })} />
          <AirlineChips label="제외 항공사" value={prefs.exclude_airlines} onChange={(v) => set({ exclude_airlines: v })} />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="cf-maxprice" className="text-sm font-medium">
                최대 가격 (원)
              </Label>
              <Input
                id="cf-maxprice"
                type="number"
                inputMode="numeric"
                min={1}
                value={prefs.max_price ?? ""}
                onChange={(e) => set({ max_price: numOrNull(e.target.value) })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cf-maxdur" className="text-sm font-medium">
                최대 비행시간 (분)
              </Label>
              <Input
                id="cf-maxdur"
                type="number"
                inputMode="numeric"
                min={1}
                value={prefs.max_duration_min ?? ""}
                onChange={(e) => set({ max_duration_min: numOrNull(e.target.value) })}
              />
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
