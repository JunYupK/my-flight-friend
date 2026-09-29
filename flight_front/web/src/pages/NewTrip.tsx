import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createTrip } from "../api";
import type { Preferences } from "../types";

const IATA = /^[A-Z]{3}$/;
const inputCls =
  "w-full min-w-0 rounded-xl bg-apple-surface border border-apple-text/10 px-3 py-2 text-sm text-apple-text";

function windowOf(from: string, to: string): [string, string] | null {
  return from && to ? [from, to] : null;
}

function WindowInput(props: {
  label: string;
  from: string;
  to: string;
  onFrom: (v: string) => void;
  onTo: (v: string) => void;
}) {
  return (
    <div>
      <span className="block text-xs text-apple-secondary mb-1">{props.label}</span>
      <div className="flex items-center gap-2">
        <input type="time" value={props.from} onChange={(e) => props.onFrom(e.target.value)} className={inputCls} />
        <span className="text-apple-secondary">~</span>
        <input type="time" value={props.to} onChange={(e) => props.onTo(e.target.value)} className={inputCls} />
      </div>
    </div>
  );
}

export default function NewTrip() {
  const navigate = useNavigate();
  const [destination, setDestination] = useState("");
  const [outDate, setOutDate] = useState("");
  const [retDate, setRetDate] = useState("");
  const [outFrom, setOutFrom] = useState("");
  const [outTo, setOutTo] = useState("");
  const [inFrom, setInFrom] = useState("");
  const [inTo, setInTo] = useState("");
  const [nonstop, setNonstop] = useState(false);
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!IATA.test(destination)) return setError("목적지는 IATA 공항 코드 3자리(예: NRT)로 입력하세요.");
    if (!outDate || !retDate) return setError("출국일과 귀국일을 입력하세요.");
    if (retDate <= outDate) return setError("귀국일은 출국일 이후여야 합니다.");
    const targetPrice = target === "" ? null : Number(target);
    if (targetPrice !== null && (!Number.isInteger(targetPrice) || targetPrice <= 0)) {
      return setError("목표가는 양의 정수(원)로 입력하세요.");
    }
    const prefs: Preferences = {
      out_dep_window: windowOf(outFrom, outTo),
      in_dep_window: windowOf(inFrom, inTo),
      nonstop_only: nonstop,
      include_airlines: [],
      exclude_airlines: [],
      max_price: null,
      max_duration_min: null,
    };
    setSubmitting(true);
    try {
      const res = await createTrip({
        destination,
        out_date: outDate,
        ret_date: retDate,
        prefs,
        target_price: targetPrice,
      });
      navigate(`/trips/${res.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "여행 생성에 실패했습니다.");
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="max-w-md mx-auto space-y-4">
      <h1 className="text-xl font-semibold text-apple-text">새 여행</h1>
      <label className="block">
        <span className="block text-xs text-apple-secondary mb-1">목적지 (IATA 3자리)</span>
        <input
          value={destination}
          onChange={(e) => setDestination(e.target.value.toUpperCase())}
          maxLength={3}
          placeholder="NRT"
          autoCapitalize="characters"
          className={inputCls}
        />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block min-w-0">
          <span className="block text-xs text-apple-secondary mb-1">출국일</span>
          <input type="date" value={outDate} onChange={(e) => setOutDate(e.target.value)} className={inputCls} />
        </label>
        <label className="block min-w-0">
          <span className="block text-xs text-apple-secondary mb-1">귀국일</span>
          <input type="date" value={retDate} onChange={(e) => setRetDate(e.target.value)} className={inputCls} />
        </label>
      </div>
      <fieldset className="space-y-3 border-t border-apple-text/10 pt-4">
        <legend className="text-xs text-apple-secondary pr-2">선호 조건 (선택)</legend>
        <WindowInput label="출국편 출발 시간대" from={outFrom} to={outTo} onFrom={setOutFrom} onTo={setOutTo} />
        <WindowInput label="귀국편 출발 시간대" from={inFrom} to={inTo} onFrom={setInFrom} onTo={setInTo} />
        <label className="flex items-center gap-2 text-sm text-apple-text">
          <input type="checkbox" checked={nonstop} onChange={(e) => setNonstop(e.target.checked)} />
          직항만
        </label>
        <label className="block">
          <span className="block text-xs text-apple-secondary mb-1">목표가 (원)</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className={inputCls}
          />
        </label>
      </fieldset>
      {error && <p className="text-sm text-apple-red whitespace-pre-line">{error}</p>}
      <button
        type="submit"
        disabled={submitting}
        className="w-full px-4 py-2 bg-apple-blue text-apple-bg rounded-full text-sm font-medium disabled:opacity-40"
      >
        {submitting ? "생성 중…" : "추적 시작"}
      </button>
    </form>
  );
}
