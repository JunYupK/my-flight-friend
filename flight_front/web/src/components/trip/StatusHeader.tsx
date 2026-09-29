import type { TripView } from "../../types";
import { dday, timeAgo } from "../../utils";
import { providerLabel } from "./providers";
import type { ProviderMark } from "./providers";

interface Props {
  view: TripView;
  marks: ProviderMark[];
  running: boolean;
  cooldown: number;
  starting: boolean;
  error: string;
  onCheck: () => void;
}

function Mark({ m }: { m: ProviderMark }) {
  const name = providerLabel(m.provider);
  if (m.state === "pending") return <span className="text-apple-secondary">{name} 진행 중</span>;
  if (m.state === "ok") return <span>{name} <span className="text-green-600">✓</span></span>;
  return (
    <span>
      {name} <span className="text-red-500">✕</span>
      <span className="text-apple-secondary">({m.reason})</span>
    </span>
  );
}

export default function StatusHeader({ view, marks, running, cooldown, starting, error, onCheck }: Props) {
  const { trip, providers } = view;
  const lastObserved = providers.map((p) => p.observed_at).sort().pop();
  const disabled = running || starting || cooldown > 0;
  const label = running ? "확인 중…" : cooldown > 0 ? `방금 확인됨 (${cooldown}초)` : "지금 확인";
  return (
    <section className="rounded-2xl bg-apple-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h1 className="text-lg font-semibold text-apple-text">
          {trip.origin}→{trip.destination}
        </h1>
        <span className="text-sm text-apple-secondary">
          {trip.out_date.slice(5).replace("-", "/")}→{trip.ret_date.slice(5).replace("-", "/")} · {dday(trip.days_to_departure)}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-apple-text min-w-0 break-words">
          {running ? (
            "확인 중 · "
          ) : (
            <>마지막 확인 {lastObserved ? timeAgo(lastObserved) : "없음"}{marks.length > 0 ? " · " : ""}</>
          )}
          {marks.map((m, i) => (
            <span key={m.provider}>
              {i > 0 && " · "}
              <Mark m={m} />
            </span>
          ))}
        </p>
        <button
          type="button"
          onClick={onCheck}
          disabled={disabled}
          className="shrink-0 rounded-full bg-apple-text px-4 py-1.5 text-sm font-medium text-apple-bg disabled:opacity-40"
        >
          {label}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </section>
  );
}
