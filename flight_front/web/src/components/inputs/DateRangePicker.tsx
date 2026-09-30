import { useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import type { DateRange } from "react-day-picker";
import { ko } from "react-day-picker/locale/ko";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { DAY_NAMES } from "@/utils";

export interface DateRangeValue {
  from?: Date;
  to?: Date;
}

function md(d: Date): string {
  return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}(${DAY_NAMES[d.getDay()]})`;
}

function nights(from: Date, to: Date): number {
  const utc = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

export function rangeSummary(v: DateRangeValue): string | null {
  if (!v.from) return null;
  if (!v.to) return `${md(v.from)} – 귀국일 선택`;
  const n = nights(v.from, v.to);
  return `${md(v.from)} – ${md(v.to)} · ${n}박 ${n + 1}일`;
}

function useMonths(): number {
  const query = "(min-width: 768px)";
  const [wide, setWide] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setWide(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return wide ? 2 : 1;
}

export default function DateRangePicker({
  value,
  onChange,
}: {
  value: DateRangeValue;
  onChange: (v: DateRangeValue) => void;
}) {
  const [open, setOpen] = useState(false);
  const months = useMonths();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const summary = rangeSummary(value);

  const handleSelect = (_: DateRange | undefined, day: Date) => {
    const { from, to } = value;
    // 출발일만 골라진 상태에서 그 이후 날짜를 누르면 귀국일, 아니면 새로 시작
    if (from && !to && day > from) {
      onChange({ from, to: day });
      setOpen(false);
    } else {
      onChange({ from: day, to: undefined });
    }
  };

  return (
    <div className="space-y-1.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" className="w-full justify-start font-normal">
            <CalendarDays />
            {summary ?? <span className="text-muted-foreground">출국일 – 귀국일 선택</span>}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-0">
          <Calendar
            mode="range"
            locale={ko}
            numberOfMonths={months}
            selected={value as DateRange}
            onSelect={handleSelect}
            defaultMonth={value.from ?? today}
            disabled={[{ before: today }, ...(value.from && !value.to ? [{ before: new Date(value.from.getFullYear(), value.from.getMonth(), value.from.getDate() + 1) }] : [])]}
          />
          {value.from && (
            <div className="flex justify-end border-t px-3 py-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => onChange({})}>
                날짜 초기화
              </Button>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}
