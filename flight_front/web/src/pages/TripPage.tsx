import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Hourglass } from "lucide-react";
import { toast } from "sonner";
import { getRun, getTrip, startRun } from "../api";
import type { RunStatus, TripView } from "../types";
import EmptyState from "@/components/common/EmptyState";
import ErrorState from "@/components/common/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import BestComboHero from "../components/trip/BestComboHero";
import CandidateChips from "../components/trip/CandidateChips";
import HistoryChart from "../components/trip/HistoryChart";
import NearMissLine from "../components/trip/NearMissLine";
import Results from "../components/trip/Results";
import RunProgress from "../components/trip/RunProgress";
import SelectionBar from "../components/trip/SelectionBar";
import TripHeader from "../components/trip/TripHeader";
import TripSettingsSheet from "../components/trip/TripSettingsSheet";
import { PROVIDERS } from "@/lib/providers";

const POLL_MS = 2000;

function errText(e: unknown): string {
  return e instanceof Error ? e.message : "알 수 없는 오류";
}

export default function TripPage() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const [trip, setTrip] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [jump, setJump] = useState<{ dir: "out" | "in"; key: string; n: number } | null>(null);
  const [selOut, setSelOut] = useState<string | null>(null);
  const [selIn, setSelIn] = useState<string | null>(null);

  // 선택 유지: TripView가 교체돼도 각 쪽의 키가 남아 있고 가격이 있으면 유지, 사라진 쪽만 첫 후보로 대체
  useEffect(() => {
    if (!trip) return;
    const ok = (legs: TripView["legs"]["out"], k: string | null) =>
      k !== null && legs.some((l) => l.flight_key === k && l.best_price != null);
    const first = trip.candidates[0];
    if (!ok(trip.legs.out, selOut)) {
      const next = first ? first.out_flight_key : null;
      if (next !== selOut) setSelOut(next);
    }
    if (!ok(trip.legs.in, selIn)) {
      const next = first ? first.in_flight_key : null;
      if (next !== selIn) setSelIn(next);
    }
  }, [trip, selOut, selIn]);

  // 로드 (id 변경 시 상태 초기화). 열린 run이 있으면 자동 폴링.
  useEffect(() => {
    let cancelled = false;
    setTrip(null);
    setLoading(true);
    setError("");
    setRunId(null);
    setRun(null);
    setCooldown(0);
    setSettingsOpen(false);
    setJump(null);
    setSelOut(null);
    setSelIn(null);
    getTrip(id)
      .then((v) => {
        if (cancelled) return;
        setTrip(v);
        if (v.run && (v.run.status === "queued" || v.run.status === "running")) setRunId(v.run.id);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errText(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  // 폴링
  useEffect(() => {
    if (runId === null) return;
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const r = await getRun(runId);
        if (cancelled) return;
        setRun(r);
        if (r.status === "done" || r.status === "error") {
          const v = await getTrip(id);
          if (cancelled) return;
          setTrip(v);
          setRunId(null);
          setRun(null);
          return;
        }
      } catch (e: unknown) {
        if (cancelled) return;
        toast.error(errText(e));
      }
      timer = window.setTimeout(tick, POLL_MS);
    };
    timer = window.setTimeout(tick, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [runId, id]);

  // 쿨다운 카운트다운
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => window.clearTimeout(t);
  }, [cooldown]);

  const onCheck = useCallback(async () => {
    setStarting(true);
    try {
      const r = await startRun(id);
      if (r.kind === "started") setRunId(r.runId);
      else setCooldown(Math.max(1, Math.ceil(r.cooldownSeconds)));
    } catch (e: unknown) {
      toast.error(errText(e));
    } finally {
      setStarting(false);
    }
  }, [id]);

  if (!Number.isInteger(id)) return <ErrorState message="잘못된 여행 주소입니다." />;
  if (loading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-56 w-full rounded-2xl" />
      </div>
    );
  if (error || !trip) return <ErrorState message={error || "여행을 찾을 수 없습니다."} />;

  const running = runId !== null;
  const selOutLeg = trip.legs.out.find((l) => l.flight_key === selOut) ?? null;
  const selInLeg = trip.legs.in.find((l) => l.flight_key === selIn) ?? null;
  const pick = (outKey: string, inKey: string) => {
    setSelOut(outKey);
    setSelIn(inKey);
  };
  const jumpTo = (dir: "out" | "in", key: string) => setJump((j) => ({ dir, key, n: (j?.n ?? 0) + 1 }));
  const refreshKey = JSON.stringify(trip.trip.prefs) + String(trip.stats.current ?? "") + (trip.run ? `${trip.run.id}:${trip.run.status}` : "");
  const noLegs = trip.legs.out.length === 0 && trip.legs.in.length === 0;
  const providerIds = Array.from(
    new Set([...trip.providers.map((p) => p.provider), ...(run?.snapshots ?? []).map((s) => s.provider), ...Object.keys(PROVIDERS)]),
  );

  return (
    <div className={`space-y-5 ${selOutLeg && selInLeg ? "pb-28" : ""}`}>
      <TripHeader
        view={trip}
        onRun={onCheck}
        running={running || starting}
        cooldownSeconds={cooldown > 0 ? cooldown : null}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      {running && <RunProgress snapshots={run?.snapshots ?? []} providers={providerIds} />}
      {noLegs && !running && (
        <EmptyState
          icon={Hourglass}
          title="아직 확인 전이에요"
          description="‘지금 확인’을 누르면 가격을 가져와요."
        />
      )}
      {!noLegs && (
        <>
          <BestComboHero view={trip} onSelect={pick} onJump={jumpTo} />
          <CandidateChips candidates={trip.candidates} legs={trip.legs} onSelect={pick} />
          <NearMissLine nearMiss={trip.near_miss} legs={trip.legs} onJump={jumpTo} />
        </>
      )}
      <HistoryChart tripId={trip.trip.id} refreshKey={refreshKey} />
      {!noLegs && (
        <Results
          view={trip}
          selOut={selOut}
          selIn={selIn}
          onSelectOut={setSelOut}
          onSelectIn={setSelIn}
          jump={jump}
          onApplied={(v) => {
            if (v.trip.id === id) setTrip(v);
          }}
        />
      )}
      {selOutLeg && selInLeg && (
        <SelectionBar
          out={selOutLeg}
          inn={selInLeg}
          outDate={trip.trip.out_date}
          retDate={trip.trip.ret_date}
          rtReference={trip.rt_reference}
        />
      )}
      <TripSettingsSheet
        view={trip}
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        onSaved={(v) => {
          if (v.trip.id === id) setTrip(v);
        }}
      />
    </div>
  );
}
