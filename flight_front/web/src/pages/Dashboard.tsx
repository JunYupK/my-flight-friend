import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Plane, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { listTrips, refreshAll } from "@/api";
import AppShell from "@/components/layout/AppShell";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import DashboardTripCard from "@/components/dashboard/DashboardTripCard";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import type { TripSummary } from "@/types";

const grid = "grid grid-cols-1 gap-4 lg:grid-cols-2";

function byDeparture(a: TripSummary, b: TripSummary): number {
  return a.out_date.localeCompare(b.out_date);
}

function byTrackingThenDeparture(a: TripSummary, b: TripSummary): number {
  return Number(b.tracking) - Number(a.tracking) || byDeparture(a, b);
}

function refreshMessage(queued: number, cooldown: number, running: number): string {
  const parts: string[] = [];
  if (queued > 0) parts.push(`${queued}개 확인 요청`);
  if (cooldown > 0) parts.push(`${cooldown}개 쿨다운`);
  if (running > 0) parts.push(`${running}개 진행 중`);
  return parts.join(" · ");
}

export default function Dashboard() {
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    return listTrips()
      .then((t) => {
        setTrips(t);
        setError("");
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const polling = trips?.some((t) => t.open_run_id != null) ?? false;
  useEffect(() => {
    if (!polling) return;
    const id = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(id);
  }, [polling, load]);

  async function onRefreshAll() {
    setRefreshing(true);
    try {
      const r = await refreshAll();
      const cooldown = r.skipped.filter((s) => s.reason === "cooldown").length;
      const running = r.skipped.filter((s) => s.reason === "running").length;
      toast(refreshMessage(r.queued.length, cooldown, running) || "확인할 여행이 없습니다");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "요청 실패");
    } finally {
      setRefreshing(false);
    }
  }

  const actions = (
    <>
      <Button asChild variant="ghost" size="sm" aria-label="새 Trip" title="새 Trip">
        <Link to="/trips/new">
          <Plus />
          <span className="hidden sm:inline">새 Trip</span>
        </Link>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        aria-label="전체 다시 확인"
        title="전체 다시 확인"
        onClick={() => void onRefreshAll()}
        disabled={refreshing}
      >
        <RefreshCw className={refreshing ? "animate-spin" : undefined} />
        <span className="hidden sm:inline">전체 다시 확인</span>
      </Button>
    </>
  );

  let body;
  if (error && !trips) {
    body = <ErrorState message={error} onRetry={() => void load()} />;
  } else if (!trips) {
    body = (
      <div className={grid}>
        <Skeleton className="h-72 rounded-2xl" />
        <Skeleton className="h-72 rounded-2xl" />
      </div>
    );
  } else if (trips.length === 0) {
    body = (
      <EmptyState
        icon={Plane}
        title="첫 여행을 저장해 보세요"
        description="목적지와 날짜를 정하면 최저가를 대신 지켜봐 드려요."
        action={
          <Button asChild>
            <Link to="/trips/new">
              <Plus />새 Trip
            </Link>
          </Button>
        }
      />
    );
  } else {
    const active = trips.filter((t) => !t.archived).sort(byTrackingThenDeparture);
    const archived = trips.filter((t) => t.archived).sort(byDeparture);
    body = (
      <div className="space-y-8">
        {active.length > 0 && (
          <div className={grid}>
            {active.map((t) => (
              <DashboardTripCard key={t.id} trip={t} />
            ))}
          </div>
        )}
        {archived.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger className="group flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
              지난 여행 ({archived.length})
              <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" />
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3">
              <div className={grid}>
                {archived.map((t) => (
                  <DashboardTripCard key={t.id} trip={t} />
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>
    );
  }

  return (
    <AppShell actions={actions}>
      <h1 className="mb-4 text-xl font-semibold">내 여행</h1>
      {body}
    </AppShell>
  );
}
