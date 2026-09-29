import { useEffect, useRef, useState } from "react";
import { patchTrip } from "../../api";
import type { MergedLegView, Preferences, TripView } from "../../types";

interface Props {
  tripId: number;
  prefs: Preferences;
  legs: { out: MergedLegView[]; in: MergedLegView[] };
  onApplied: (v: TripView) => void;
}

interface Form {
  outFrom: string;
  outTo: string;
  inFrom: string;
  inTo: string;
  nonstop: boolean;
  include: string[];
  exclude: string[];
  maxPrice: string;
  maxHours: string;
}

const DEBOUNCE_MS = 400;
const inputCls =
  "w-full min-w-0 rounded-lg bg-apple-bg border border-apple-text/10 px-2 py-1.5 text-sm text-apple-text";

function toForm(p: Preferences): Form {
  return {
    outFrom: p.out_dep_window ? p.out_dep_window[0] : "",
    outTo: p.out_dep_window ? p.out_dep_window[1] : "",
    inFrom: p.in_dep_window ? p.in_dep_window[0] : "",
    inTo: p.in_dep_window ? p.in_dep_window[1] : "",
    nonstop: p.nonstop_only,
    include: p.include_airlines,
    exclude: p.exclude_airlines,
    maxPrice: p.max_price != null ? String(p.max_price) : "",
    maxHours: p.max_duration_min != null ? String(p.max_duration_min / 60) : "",
  };
}

function windowOf(a: string, b: string): [string, string] | null {
  return a && b ? [a, b] : null;
}

function positive(s: string): number | null {
  const n = Number(s);
  return s.trim() !== "" && isFinite(n) && n > 0 ? n : null;
}

function toPrefs(f: Form): Preferences {
  const price = positive(f.maxPrice);
  const hours = positive(f.maxHours);
  return {
    out_dep_window: windowOf(f.outFrom, f.outTo),
    in_dep_window: windowOf(f.inFrom, f.inTo),
    nonstop_only: f.nonstop,
    include_airlines: f.include,
    exclude_airlines: f.exclude,
    max_price: price != null ? Math.round(price) : null,
    max_duration_min: hours != null ? Math.round(hours * 60) : null,
  };
}

function airlinesIn(legs: { out: MergedLegView[]; in: MergedLegView[] }, f: Form): { iata: string; name: string }[] {
  const map = new Map<string, string>();
  for (const l of [...legs.out, ...legs.in]) {
    if (l.airline_iata && !map.has(l.airline_iata)) map.set(l.airline_iata, l.airline_name ?? l.airline_iata);
  }
  for (const c of [...f.include, ...f.exclude]) if (!map.has(c)) map.set(c, c);
  return [...map.entries()].map(([iata, name]) => ({ iata, name })).sort((a, b) => a.name.localeCompare(b.name));
}

export default function FilterBar({ tripId, prefs, legs, onApplied }: Props) {
  const [form, setForm] = useState<Form>(() => toForm(prefs));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const seq = useRef(0);

  // 다른 trip으로 이동하면 폼 초기화 (prefs는 이 바에서만 바뀌므로 id 기준으로만 동기화)
  useEffect(() => {
    setForm(toForm(prefs));
    setError("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  function apply(next: Form) {
    const mine = ++seq.current;
    setSaving(true);
    setError("");
    patchTrip(tripId, { prefs: toPrefs(next) })
      .then((v) => {
        if (mine === seq.current) onApplied(v);
      })
      .catch((e: unknown) => {
        if (mine === seq.current) setError(e instanceof Error ? e.message : "저장 실패");
      })
      .finally(() => {
        if (mine === seq.current) setSaving(false);
      });
  }

  function change(patch: Partial<Form>, immediate: boolean) {
    const next = { ...form, ...patch };
    setForm(next);
    window.clearTimeout(timer.current);
    if (immediate) apply(next);
    else timer.current = window.setTimeout(() => apply(next), DEBOUNCE_MS);
  }

  function cycleAirline(code: string) {
    if (form.include.includes(code)) {
      change({ include: form.include.filter((c) => c !== code), exclude: [...form.exclude, code] }, true);
    } else if (form.exclude.includes(code)) {
      change({ exclude: form.exclude.filter((c) => c !== code) }, true);
    } else {
      change({ include: [...form.include, code] }, true);
    }
  }

  const airlines = airlinesIn(legs, form);
  const label = "mb-1 block text-xs text-apple-secondary";
  return (
    <section className="rounded-2xl bg-apple-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-apple-text">선호 조건</h2>
        <span className="text-xs text-apple-secondary">{saving ? "저장 중…" : "변경 즉시 반영"}</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <span className={label}>출국 출발 시간대</span>
          <div className="flex items-center gap-2">
            <input type="time" value={form.outFrom} onChange={(e) => change({ outFrom: e.target.value }, false)} className={inputCls} aria-label="출국 시작" />
            <span className="text-apple-secondary">~</span>
            <input type="time" value={form.outTo} onChange={(e) => change({ outTo: e.target.value }, false)} className={inputCls} aria-label="출국 끝" />
          </div>
        </div>
        <div>
          <span className={label}>귀국 출발 시간대</span>
          <div className="flex items-center gap-2">
            <input type="time" value={form.inFrom} onChange={(e) => change({ inFrom: e.target.value }, false)} className={inputCls} aria-label="귀국 시작" />
            <span className="text-apple-secondary">~</span>
            <input type="time" value={form.inTo} onChange={(e) => change({ inTo: e.target.value }, false)} className={inputCls} aria-label="귀국 끝" />
          </div>
        </div>
        <div>
          <label className={label} htmlFor="ff-max-price">최대 가격(원, 왕복 합)</label>
          <input id="ff-max-price" type="number" inputMode="numeric" min={0} value={form.maxPrice} onChange={(e) => change({ maxPrice: e.target.value }, false)} className={inputCls} />
        </div>
        <div>
          <label className={label} htmlFor="ff-max-dur">최대 소요시간(시간)</label>
          <input id="ff-max-dur" type="number" inputMode="decimal" min={0} step={0.5} value={form.maxHours} onChange={(e) => change({ maxHours: e.target.value }, false)} className={inputCls} />
        </div>
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-apple-text">
        <input type="checkbox" checked={form.nonstop} onChange={(e) => change({ nonstop: e.target.checked }, true)} />
        직항만
      </label>
      {airlines.length > 0 && (
        <div className="mt-3">
          <span className={label}>항공사 (탭: 포함 → 제외 → 해제)</span>
          <div className="flex flex-wrap gap-1.5">
            {airlines.map((a) => {
              const inc = form.include.includes(a.iata);
              const exc = form.exclude.includes(a.iata);
              const cls = inc
                ? "bg-apple-blue text-white"
                : exc
                  ? "bg-apple-red/15 text-apple-red line-through"
                  : "bg-apple-text/5 text-apple-secondary";
              return (
                <button key={a.iata} type="button" onClick={() => cycleAirline(a.iata)} className={`rounded-full px-2.5 py-1 text-xs ${cls}`} title={a.iata}>
                  {inc ? "✓ " : exc ? "✕ " : ""}
                  {a.name}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </section>
  );
}
