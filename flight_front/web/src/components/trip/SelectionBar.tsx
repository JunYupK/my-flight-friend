import type { MergedLegView, RtReference } from "../../types";
import { providerLabel } from "@/lib/providers";
import { formatStay, formatWon, stayMinutes } from "../../utils";

interface Props {
  out: MergedLegView;
  inn: MergedLegView;
  outDate: string;
  retDate: string;
  rtReference: RtReference[];
}

function cheapestUrl(leg: MergedLegView): string | null {
  let best: { price: number; url: string | null } | null = null;
  for (const p of leg.prices) {
    if (p.stale || p.price == null) continue;
    if (best === null || p.price < best.price) best = { price: p.price, url: p.booking_url };
  }
  return best ? best.url : null;
}

function BookLink({ href, label }: { href: string | null; label: string }) {
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-full bg-apple-blue px-3 py-1.5 text-xs font-medium text-white hover:bg-apple-blue-hover"
    >
      {label} ↗
    </a>
  );
}

export default function SelectionBar({ out, inn, outDate, retDate, rtReference }: Props) {
  if (out.best_price == null || inn.best_price == null) return null;
  const total = out.best_price + inn.best_price;
  const stay =
    out.dep_time && out.arr_time && inn.dep_time
      ? stayMinutes(outDate, out.dep_time, out.arr_time, retDate, inn.dep_time)
      : null;
  const rt = rtReference.find((r) => r.airline_iata === out.airline_iata && r.diff != null);
  const diff = rt?.diff ?? null;
  const hasCond = out.best_cond != null || inn.best_cond != null;
  const condTotal = hasCond
    ? Math.min(out.best_cond?.price ?? out.best_price, out.best_price) +
      Math.min(inn.best_cond?.price ?? inn.best_price, inn.best_price)
    : null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-apple-text/10 bg-apple-surface/95 backdrop-blur-xl">
      <div className="mx-auto max-w-5xl px-4 py-2 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <p className="min-w-0 text-sm text-apple-text">
            <span className="text-base font-semibold">{formatWon(total)}</span>
            {stay != null && (
              <span className={stay < 0 ? "text-apple-orange" : "text-apple-secondary"}>
                {" "}
                · 현지 {stay < 0 ? "일정 겹침" : formatStay(stay)}
              </span>
            )}
          </p>
          <div className="flex gap-2">
            <BookLink href={cheapestUrl(out)} label="출국편 예약" />
            <BookLink href={cheapestUrl(inn)} label="귀국편 예약" />
          </div>
        </div>
        {condTotal != null && (
          <p className="mt-1 text-xs text-apple-blue">
            카드 조건 적용 시 최저 합계 {formatWon(condTotal)}
            <span className="ml-1 text-apple-secondary">편마다 카드 조건이 다를 수 있어요</span>
          </p>
        )}
        {rt && diff != null && (
          <p className="mt-1 text-xs text-apple-secondary">
            이 항공사 왕복으로 사면 총 {formatWon(rt.rt_min)}부터 ({providerLabel(rt.rt_provider)}
            {rt.cond_rt_min != null && ` · 카드 조건 시 ${formatWon(rt.cond_rt_min)}`}
            {" · "}편도 합보다 {formatWon(Math.abs(diff))} {diff >= 0 ? "저렴" : "비쌈"})
          </p>
        )}
      </div>
    </div>
  );
}
