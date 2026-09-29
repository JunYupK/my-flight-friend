import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getRun, getTrip, startRun } from "../api";
import type { CandidateView, RunStatus, TripView } from "../types";
import StatusHeader from "../components/trip/StatusHeader";
import TripSettings from "../components/trip/TripSettings";
import TrackingSummary from "../components/trip/TrackingSummary";
import HistoryChart from "../components/trip/HistoryChart";
import Results from "../components/trip/Results";
import SelectionBar from "../components/trip/SelectionBar";
import { marksFromRun, marksFromStatuses, providerLabel } from "../components/trip/providers";
import type { ProviderMark } from "../components/trip/providers";

const POLL_MS = 2500;

function errText(e: unknown): string {
  return e instanceof Error ? e.message : "알 수 없는 오류";
}

function RunProgress({ marks }: { marks: ProviderMark[] }) {
  return (
    <section className="rounded-2xl bg-apple-surface p-4 text-sm">
      <p className="font-medium text-apple-text">첫 검색 진행 중…</p>
      <ul className="mt-2 space-y-1 text-apple-secondary">
        {marks.map((m) => (
          <li key={m.provider}>
            {providerLabel(m.provider)}{" "}
            {m.state === "pending" ? "진행 중" : m.state === "ok" ? "✓" : `✕(${m.reason})`}
          </li>
        ))}
      </ul>
    </section>
  );
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
  const [actionError, setActionError] = useState("");
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
    setActionError("");
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
        setActionError(errText(e));
      }
      timer = window.setTimeout(tick, POLL_MS);
    };
    timer = window.setTimeout(tick, POLL_MS);
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
    setActionError("");
    try {
      const r = await startRun(id);
      if (r.kind === "started") setRunId(r.runId);
      else setCooldown(Math.max(1, Math.ceil(r.cooldownSeconds)));
    } catch (e: unknown) {
      setActionError(errText(e));
    } finally {
      setStarting(false);
    }
  }, [id]);

  if (!Number.isInteger(id)) return <p className="text-sm text-red-500">잘못된 여행 주소입니다.</p>;
  if (loading) return <p className="text-sm text-apple-secondary">불러오는 중…</p>;
  if (error || !trip) return <p className="text-sm text-red-500">{error || "여행을 찾을 수 없습니다."}</p>;

  const running = runId !== null;
  const marks = running ? marksFromRun(run, trip.providers) : marksFromStatuses(trip.providers);
  const selOutLeg = trip.legs.out.find((l) => l.flight_key === selOut) ?? null;
  const selInLeg = trip.legs.in.find((l) => l.flight_key === selIn) ?? null;
  const pickCandidate = (c: CandidateView) => {
    setSelOut(c.out_flight_key);
    setSelIn(c.in_flight_key);
  };
  const refreshKey = JSON.stringify(trip.trip.prefs) + String(trip.stats.current ?? "") + (trip.run ? `${trip.run.id}:${trip.run.status}` : "");
  const noLegs = trip.legs.out.length === 0 && trip.legs.in.length === 0;

  return (
    <div className={`space-y-4 ${selOutLeg && selInLeg ? "pb-28" : ""}`}>
      <StatusHeader
        view={trip}
        marks={marks}
        running={running}
        cooldown={cooldown}
        starting={starting}
        error={actionError}
        onCheck={onCheck}
      />
      <TripSettings
        trip={trip.trip}
        onApplied={(v) => {
          if (v.trip.id === id) setTrip(v);
        }}
      />
      <TrackingSummary stats={trip.stats} />
      <HistoryChart tripId={trip.trip.id} refreshKey={refreshKey} />
      {noLegs && running && <RunProgress marks={marks} />}
      {!noLegs && (
        <Results
          view={trip}
          selOut={selOut}
          selIn={selIn}
          onSelectOut={setSelOut}
          onSelectIn={setSelIn}
          onPick={pickCandidate}
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
    </div>
  );
}
