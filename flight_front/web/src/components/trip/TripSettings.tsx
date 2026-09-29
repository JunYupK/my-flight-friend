import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { patchTrip } from "../../api";
import type { TripInfo, TripPatchInput, TripView } from "../../types";

interface Props {
  trip: TripInfo;
  onApplied: (v: TripView) => void;
}

const inputCls =
  "w-32 min-w-0 rounded-lg bg-apple-bg border border-apple-text/10 px-2 py-1.5 text-sm text-apple-text";

function targetText(t: TripInfo): string {
  return t.target_price != null ? String(t.target_price) : "";
}

export default function TripSettings({ trip, onApplied }: Props) {
  const tripId = trip.id;
  const [target, setTarget] = useState(() => targetText(trip));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const seq = useRef(0);

  // 다른 trip으로 이동하면 입력 초기화하고 진행 중 응답을 무효화
  useEffect(() => {
    setTarget(targetText(trip));
    setError("");
    setSaving(false);
    return () => {
      seq.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  function save(patch: TripPatchInput, after?: (v: TripView) => void) {
    const mine = ++seq.current;
    setSaving(true);
    setError("");
    patchTrip(tripId, patch)
      .then((v) => {
        if (mine !== seq.current || v.trip.id !== tripId) return;
        onApplied(v);
        after?.(v);
      })
      .catch((e: unknown) => {
        if (mine === seq.current) setError(e instanceof Error ? e.message : "저장 실패");
      })
      .finally(() => {
        if (mine === seq.current) setSaving(false);
      });
  }

  function submitTarget(e: FormEvent) {
    e.preventDefault();
    const text = target.trim();
    const value = text === "" ? null : Number(text);
    if (value !== null && (!Number.isInteger(value) || value <= 0)) {
      setError("목표가는 양의 정수(원)로 입력하세요. 비우면 해제됩니다.");
      return;
    }
    save({ target_price: value }, (v) => setTarget(targetText(v.trip)));
  }

  return (
    <section className="rounded-2xl bg-apple-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <label className="flex items-center gap-2 text-sm text-apple-text">
          <input
            type="checkbox"
            role="switch"
            checked={trip.tracking}
            disabled={saving}
            onChange={(e) => save({ tracking: e.target.checked })}
          />
          추적 {trip.tracking ? "켜짐" : "꺼짐"}
        </label>
        <form onSubmit={submitTarget} className="flex items-center gap-2">
          <label htmlFor="ff-target" className="text-xs text-apple-secondary">
            목표가(원)
          </label>
          <input
            id="ff-target"
            type="number"
            inputMode="numeric"
            min={1}
            placeholder="없음"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className={inputCls}
          />
          <button
            type="submit"
            disabled={saving}
            className="rounded-full bg-apple-blue px-3 py-1.5 text-xs font-medium text-apple-bg disabled:opacity-40"
          >
            {saving ? "저장 중…" : "저장"}
          </button>
        </form>
      </div>
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </section>
  );
}
