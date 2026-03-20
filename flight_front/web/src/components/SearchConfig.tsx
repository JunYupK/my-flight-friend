import React from "react";
import type { SearchConfig } from "../types";

interface Props {
  value: SearchConfig;
  onChange: (v: SearchConfig) => void;
}

function NumInput({
  label,
  value,
  onChange,
  min,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  step?: number;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-apple-secondary">{label}</span>
      <input
        type="number"
        min={min ?? 0}
        step={step ?? 1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-apple-bg rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-apple-blue/30 transition-shadow"
      />
    </label>
  );
}

export default function SearchConfigForm({ value, onChange }: Props) {
  const set = <K extends keyof SearchConfig>(k: K, v: SearchConfig[K]) =>
    onChange({ ...value, [k]: v });

  const toggleStay = (n: number) => {
    const s = new Set(value.stay_durations);
    s.has(n) ? s.delete(n) : s.add(n);
    set("stay_durations", Array.from(s).sort((a, b) => a - b));
  };

  return (
    <section className="bg-white rounded-2xl shadow-apple p-5 sm:p-6 space-y-8">
      <h2 className="text-base font-semibold text-apple-text">검색 설정</h2>

      {/* 알림 설정 */}
      <div>
        <h3 className="text-[11px] font-medium text-apple-secondary uppercase tracking-wider mb-3">
          알림 설정
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <NumInput
            label="목표가 (KRW)"
            value={value.target_price_krw}
            onChange={(v) => set("target_price_krw", v)}
          />
          <NumInput
            label="알림 쿨다운 (시간)"
            value={value.alert_cooldown_hours}
            onChange={(v) => set("alert_cooldown_hours", v)}
          />
          <NumInput
            label="재알림 최소 하락 (KRW)"
            value={value.alert_realert_drop_krw}
            onChange={(v) => set("alert_realert_drop_krw", v)}
          />
        </div>
      </div>

      {/* 여행 일정 */}
      <div>
        <h3 className="text-[11px] font-medium text-apple-secondary uppercase tracking-wider mb-3">
          여행 일정
        </h3>
        <div>
          <span className="text-xs text-apple-secondary block mb-2">체류 일수</span>
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: 30 }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                onClick={() => toggleStay(n)}
                className={`w-8 h-8 rounded-lg text-xs font-medium transition-all duration-200 ${
                  value.stay_durations.includes(n)
                    ? "bg-apple-blue text-white shadow-apple-sm"
                    : "bg-apple-bg text-apple-secondary hover:text-apple-text"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
