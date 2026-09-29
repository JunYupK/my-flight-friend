import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listTrips } from "../api";
import type { TripSummary } from "../types";
import { formatWon, timeAgo } from "../utils";
import NewTrip from "./NewTrip";

/** "2026-10-21" → "10/21" */
function md(d: string): string {
  return `${d.slice(5, 7)}/${d.slice(8, 10)}`;
}

function formatChange(pct: number): string {
  const sign = pct < 0 ? "−" : pct > 0 ? "+" : "";
  return `${sign}${Math.abs(pct).toFixed(1)}%`;
}

function dday(n: number): string {
  if (n === 0) return "D-day";
  return n > 0 ? `D-${n}` : `D+${-n}`;
}

function TripRow({ trip }: { trip: TripSummary }) {
  return (
    <li>
      <Link
        to={`/trips/${trip.id}`}
        className="block rounded-2xl bg-apple-surface px-4 py-3 hover:bg-apple-text/5 transition-colors"
      >
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-semibold text-apple-text">{trip.destination}</span>
          <span className="text-sm text-apple-secondary shrink-0">
            {md(trip.out_date)}→{md(trip.ret_date)} · {dday(trip.days_to_departure)}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 text-sm text-apple-secondary">
          {trip.current != null ? (
            <span className="font-medium text-apple-text">{formatWon(trip.current)}</span>
          ) : (
            <span>가격 수집 중</span>
          )}
          {trip.current_observed_at && <span>{timeAgo(trip.current_observed_at)}</span>}
          {trip.change_vs_start_pct != null && (
            <span>추적 시작 대비 {formatChange(trip.change_vs_start_pct)}</span>
          )}
        </div>
      </Link>
    </li>
  );
}

function byDeparture(a: TripSummary, b: TripSummary): number {
  return a.out_date.localeCompare(b.out_date);
}

export default function TripList() {
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listTrips()
      .then(setTrips)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-apple-red text-sm">{error}</p>;
  if (!trips) return <p className="text-apple-secondary text-sm">로딩 중…</p>;
  if (trips.length === 0) return <NewTrip />;

  const active = trips.filter((t) => t.tracking && !t.archived).sort(byDeparture);
  const inactive = trips.filter((t) => !t.tracking || t.archived).sort(byDeparture);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-apple-text">내 여행</h1>
        <Link to="/trips/new" className="px-4 py-1.5 bg-apple-blue text-apple-bg rounded-full text-xs font-medium">
          새 여행
        </Link>
      </div>
      {active.length === 0 ? (
        <p className="text-sm text-apple-secondary">추적 중인 여행이 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {active.map((t) => (
            <TripRow key={t.id} trip={t} />
          ))}
        </ul>
      )}
      {inactive.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm text-apple-secondary">
            추적 중지 · 지난 여행 ({inactive.length})
          </summary>
          <ul className="space-y-2 mt-3">
            {inactive.map((t) => (
              <TripRow key={t.id} trip={t} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
