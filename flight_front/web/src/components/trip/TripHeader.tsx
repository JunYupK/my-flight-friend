import { Link } from "react-router-dom";
import { ArrowLeft, Loader2, RefreshCw, Settings2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import ProviderBadge from "@/components/common/ProviderBadge";
import { cityName } from "@/data/airports";
import { STATUS_REASON } from "@/lib/providers";
import type { TripView } from "@/types";
import { dday, timeAgo } from "@/utils";

const DAY_MS = 86_400_000;

function nightsOf(out: string, ret: string): number {
  const t = (d: string) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10));
  return Math.round((t(ret) - t(out)) / DAY_MS);
}

function md(d: string): string {
  return `${d.slice(5, 7)}.${d.slice(8, 10)}`;
}

/** ISO 시각 → 브라우저 로컬 "HH:MM" */
function hhmm(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

interface Props {
  view: TripView;
  onRun: () => void;
  running: boolean;
  cooldownSeconds: number | null;
  onOpenSettings: () => void;
}

export default function TripHeader({ view, onRun, running, cooldownSeconds, onOpenSettings }: Props) {
  const { trip, providers } = view;
  const nights = nightsOf(trip.out_date, trip.ret_date);
  const lastObserved = providers.map((p) => p.observed_at).sort().pop();
  const cooling = cooldownSeconds != null && cooldownSeconds > 0;
  const label = running ? "확인 중…" : cooling ? `방금 확인됨 (${cooldownSeconds}초)` : "지금 확인";
  const showNext = trip.tracking && !trip.archived && trip.next_auto_at;

  return (
    <section className="space-y-3">
      <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground">
        <Link to="/">
          <ArrowLeft />
          목록
        </Link>
      </Button>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">
            {cityName(trip.destination) ?? trip.destination}
            {cityName(trip.destination) && <span className="text-muted-foreground"> {trip.destination}</span>}
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {md(trip.out_date)}–{md(trip.ret_date)} · {nights}박 {nights + 1}일 · {dday(trip.days_to_departure)}
          </p>
          <p className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm">
            <span>{lastObserved ? `${timeAgo(lastObserved)} 확인` : running ? "첫 확인 중…" : "아직 확인 전"}</span>
            {showNext && (
              <>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground">다음 자동 {hhmm(trip.next_auto_at as string)}</span>
              </>
            )}
            {providers.map((p) => (
              <span
                key={p.provider}
                className="inline-flex items-center gap-0.5"
                title={p.status === "ok" ? undefined : (STATUS_REASON[p.status] ?? p.status)}
              >
                <ProviderBadge provider={p.provider} />
                {p.status === "ok" ? (
                  <span className="text-emerald-600 dark:text-emerald-400">✓</span>
                ) : (
                  <X className="size-3.5 text-destructive" aria-label={STATUS_REASON[p.status] ?? p.status} />
                )}
              </span>
            ))}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button onClick={onRun} disabled={running || cooling}>
            {running ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            {label}
          </Button>
          <Button variant="outline" size="icon" aria-label="설정" onClick={onOpenSettings}>
            <Settings2 />
          </Button>
        </div>
      </div>
    </section>
  );
}
