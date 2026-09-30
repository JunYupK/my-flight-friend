import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { createTrip, patchTrip } from "@/api";
import DateRangePicker from "@/components/inputs/DateRangePicker";
import type { DateRangeValue } from "@/components/inputs/DateRangePicker";
import DestinationCombobox from "@/components/inputs/DestinationCombobox";
import ConditionFields from "@/components/trip/ConditionFields";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Preferences } from "@/types";

const EMPTY_PREFS: Preferences = {
  out_dep_window: null,
  in_dep_window: null,
  nonstop_only: false,
  include_airlines: [],
  exclude_airlines: [],
  max_price: null,
  max_duration_min: null,
};

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function Section({ title, error, children }: { title: string; error?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">{title}</h2>
      {children}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}

export default function NewTrip() {
  const navigate = useNavigate();
  const [destination, setDestination] = useState("");
  const [range, setRange] = useState<DateRangeValue>({});
  const [prefs, setPrefs] = useState<Preferences>(EMPTY_PREFS);
  const [tracking, setTracking] = useState(true);
  const [target, setTarget] = useState("");
  const [errors, setErrors] = useState<{ destination?: string; dates?: string; target?: string; form?: string }>({});
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next: typeof errors = {};
    if (!destination) next.destination = "목적지를 선택하세요.";
    if (!range.from || !range.to) next.dates = "출국일과 귀국일을 선택하세요.";
    const targetPrice = target === "" ? null : Number(target);
    if (targetPrice !== null && (!Number.isInteger(targetPrice) || targetPrice <= 0)) {
      next.target = "목표가는 양의 정수(원)로 입력하세요.";
    }
    setErrors(next);
    if (Object.keys(next).length > 0 || !range.from || !range.to) return;

    setSubmitting(true);
    let id: number;
    try {
      const res = await createTrip({
        destination,
        out_date: iso(range.from),
        ret_date: iso(range.to),
        prefs,
        target_price: tracking ? targetPrice : null,
      });
      id = res.id;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Trip 생성에 실패했습니다.";
      if (/ret_date|out_date/.test(msg)) {
        setErrors({ dates: msg.includes("past") ? "출국일이 이미 지난 날짜예요." : "귀국일은 출국일 다음 날 이후여야 해요." });
      } else {
        setErrors({ form: msg });
      }
      setSubmitting(false);
      return;
    }
    // Trip은 이미 만들어졌으므로 이후 실패해도 항상 상세로 이동 (재시도 시 중복 생성 방지)
    if (!tracking) {
      try {
        await patchTrip(id, { tracking: false });
      } catch {
        toast.error("추적 끄기에 실패했어요 · 상세 화면에서 꺼 주세요");
        navigate(`/trips/${id}`);
        return;
      }
    }
    toast("Trip을 만들었어요 · 확인 중");
    navigate(`/trips/${id}`);
  };

  return (
    <form onSubmit={submit} className="mx-auto max-w-[640px]">
      <h1 className="mb-4 text-xl font-semibold">새 Trip</h1>
      <Card className="rounded-2xl">
        <CardContent className="space-y-6">
          <Section title="목적지" error={errors.destination}>
            <DestinationCombobox
              value={destination}
              onChange={(v) => {
                setDestination(v);
                setErrors((e) => ({ ...e, destination: undefined }));
              }}
            />
          </Section>
          <Section title="날짜" error={errors.dates}>
            <DateRangePicker
              value={range}
              onChange={(v) => {
                setRange(v);
                setErrors((e) => ({ ...e, dates: undefined }));
              }}
            />
          </Section>
          <Section title="조건">
            <ConditionFields prefs={prefs} onChange={setPrefs} />
          </Section>
          <Section title="추적" error={errors.target}>
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="nt-tracking" className="text-sm font-medium">
                가격 추적
              </Label>
              <Switch id="nt-tracking" checked={tracking} onCheckedChange={setTracking} />
            </div>
            {tracking && (
              <div className="space-y-1.5">
                <Label htmlFor="nt-target" className="text-sm font-medium">
                  목표가 (원, 선택)
                </Label>
                <Input
                  id="nt-target"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  value={target}
                  onChange={(e) => {
                    setTarget(e.target.value);
                    setErrors((er) => ({ ...er, target: undefined }));
                  }}
                  aria-invalid={!!errors.target}
                />
              </div>
            )}
          </Section>
          {errors.form && (
            <p role="alert" className="whitespace-pre-line text-sm text-destructive">
              {errors.form}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "만드는 중…" : "만들기"}
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
