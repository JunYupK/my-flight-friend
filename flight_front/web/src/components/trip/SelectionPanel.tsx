import { useEffect, useState } from "react";
import { ChevronRight, ExternalLink, MousePointerClick } from "lucide-react";
import CondPriceTag from "@/components/common/CondPriceTag";
import Money from "@/components/common/Money";
import ProviderBadge from "@/components/common/ProviderBadge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { providerLabel } from "@/lib/providers";
import type { MergedLegView, RtReference } from "@/types";
import { formatStay, nightsBetween, stayMinutes } from "@/utils";

interface Props {
  out: MergedLegView | null;
  inn: MergedLegView | null;
  outDate: string;
  retDate: string;
  rtReference: RtReference[];
}

/** 신선한 가격 중 최저 제공자의 예약 링크. */
function cheapest(leg: MergedLegView): { provider: string; url: string } | null {
  let best: { price: number; provider: string; url: string } | null = null;
  for (const p of leg.prices) {
    if (p.stale || p.price == null || !p.booking_url) continue;
    if (best === null || p.price < best.price) best = { price: p.price, provider: p.provider, url: p.booking_url };
  }
  return best;
}

function condOf(leg: MergedLegView): number {
  return Math.min(leg.best_cond?.price ?? Infinity, leg.best_price ?? Infinity);
}

function LegLine({ label, leg }: { label: string; leg: MergedLegView }) {
  const overnight = leg.dep_time != null && leg.arr_time != null && leg.arr_time < leg.dep_time;
  const airline = leg.airline_name ?? leg.airline_iata ?? "항공사 미상";
  const book = cheapest(leg);
  return (
    <div className="space-y-2 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="font-semibold tabular-nums">
            {leg.dep_time ?? "--:--"} → {leg.arr_time ?? "--:--"}
            {overnight && <span className="ml-1 text-xs font-medium text-amber-600 dark:text-amber-400">+1</span>}
          </div>
          <div className="truncate text-sm text-muted-foreground" title={airline}>
            {airline}
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5">
          {leg.best_provider && <ProviderBadge provider={leg.best_provider} />}
          {leg.best_price != null && <Money value={leg.best_price} className="font-medium" />}
        </span>
      </div>
      {book && (
        <Button asChild variant="outline" size="sm" className="w-full">
          <a href={book.url} target="_blank" rel="noopener noreferrer">
            {label} {book.provider === "naver" ? "판매사 선택" : "예약"}
            <ExternalLink />
          </a>
        </Button>
      )}
    </div>
  );
}

function Details({ out, inn, outDate, retDate, rtReference }: Props & { out: MergedLegView; inn: MergedLegView }) {
  const total = (out.best_price ?? 0) + (inn.best_price ?? 0);
  const condTotal = condOf(out) + condOf(inn);
  const condLabel =
    out.best_cond && inn.best_cond
      ? out.best_cond.label === inn.best_cond.label
        ? out.best_cond.label
        : "카드 조건 혼합"
      : (out.best_cond ?? inn.best_cond)?.label ?? null;
  const stay =
    out.dep_time && out.arr_time && inn.dep_time
      ? stayMinutes(outDate, out.dep_time, out.arr_time, retDate, inn.dep_time)
      : null;
  const rt = rtReference.find((r) => r.airline_iata === out.airline_iata && r.diff != null);
  return (
    <div className="space-y-3">
      <div className="divide-y">
        <LegLine label="가는 편" leg={out} />
        <LegLine label="오는 편" leg={inn} />
      </div>
      <div className="space-y-2 border-t pt-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm text-muted-foreground">합계</span>
          <Money value={total} className="text-2xl font-bold tracking-tight" />
        </div>
        {condTotal < total && (
          <div className="flex justify-end">
            <CondPriceTag price={condTotal} label={condLabel} />
          </div>
        )}
        {stay != null && (
          <div className="flex justify-between gap-2 text-sm">
            <span className="text-muted-foreground">현지 체류</span>
            <span className={stay < 0 ? "text-amber-600 dark:text-amber-400" : ""}>
              {stay < 0 ? "일정 겹침" : formatStay(stay)}
            </span>
          </div>
        )}
        {rt && (
          <p className="text-sm text-muted-foreground">
            같은 항공사 왕복 <Money value={rt.rt_min} className="text-foreground" /> · {providerLabel(rt.rt_provider)}
          </p>
        )}
      </div>
    </div>
  );
}

export default function SelectionPanel({ out, inn, outDate, retDate, rtReference }: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const pair = out && inn && out.best_price != null && inn.best_price != null ? { out, inn } : null;
  const nights = nightsBetween(outDate, retDate);
  const hasPair = pair !== null;

  // 선택이 풀리면 시트도 닫아 둔다 — 다시 짝이 맞춰졌을 때 저절로 열리지 않게.
  useEffect(() => {
    if (!hasPair) setSheetOpen(false);
  }, [hasPair]);

  return (
    <>
      <aside className="hidden rounded-2xl border bg-card p-4 text-card-foreground shadow-sm lg:sticky lg:top-16 lg:block">
        <h2 className="text-sm font-medium text-muted-foreground">선택한 조합</h2>
        {pair ? (
          <Details out={pair.out} inn={pair.inn} outDate={outDate} retDate={retDate} rtReference={rtReference} />
        ) : (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
            <MousePointerClick className="size-6" />
            가는 편과 오는 편을 하나씩 골라 주세요.
          </div>
        )}
      </aside>
      {pair && (
        <>
          <div className="h-16 lg:hidden" aria-hidden />
          <div className="fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 backdrop-blur lg:hidden">
            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="mx-auto flex h-14 w-full max-w-[1200px] items-center justify-between gap-3 px-4 text-left"
            >
              <span className="min-w-0 truncate whitespace-nowrap">
                <span className="text-sm text-muted-foreground">합계 </span>
                <Money value={(pair.out.best_price ?? 0) + (pair.inn.best_price ?? 0)} className="text-lg font-bold" />
                <span className="text-sm text-muted-foreground"> · {nights}박</span>
              </span>
              <ChevronRight className="size-5 shrink-0 text-muted-foreground" />
            </button>
          </div>
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto lg:hidden">
              <SheetHeader>
                <SheetTitle>선택한 조합</SheetTitle>
                <SheetDescription className="sr-only">선택한 두 편과 합계, 예약 링크</SheetDescription>
              </SheetHeader>
              <div className="px-4 pb-6">
                <Details out={pair.out} inn={pair.inn} outDate={outDate} retDate={retDate} rtReference={rtReference} />
              </div>
            </SheetContent>
          </Sheet>
        </>
      )}
    </>
  );
}
