import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getRun, getTrip, startRun } from "../api";
import type { RunStatus, TripView } from "../types";
import StatusHeader from "../components/trip/StatusHeader";
import TrackingSummary from "../components/trip/TrackingSummary";
import HistoryChart from "../components/trip/HistoryChart";
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
  const noLegs = trip.legs.out.length === 0 && trip.legs.in.length === 0;

  return (
    <div className="space-y-4">
      <StatusHeader
        view={trip}
        marks={marks}
        running={running}
        cooldown={cooldown}
        starting={starting}
        error={actionError}
        onCheck={onCheck}
      />
      <TrackingSummary stats={trip.stats} />
      <HistoryChart tripId={trip.trip.id} />
      {noLegs && running && <RunProgress marks={marks} />}
    </div>
  );
}
