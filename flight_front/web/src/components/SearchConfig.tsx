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
    <label className="flex flex-col gap-1">
      <span className="text-sm text-gray-600">{label}</span>
      <input
        type="number"
        min={min ?? 0}
        step={step ?? 1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
      />
    </label>
  );
}

export default function SearchConfigForm({ value, onChange }: Props) {
  const set = <K extends keyof SearchConfig>(k: K, v: SearchConfig[K]) =>
    onChange({ ...value, [k]: v });

  // stay_durations: 1~30 칩
  const toggleStay = (n: number) => {
    const s = new Set(value.stay_durations);
    s.has(n) ? s.delete(n) : s.add(n);
    set("stay_durations", Array.from(s).sort((a, b) => a - b));
  };


  return (
    <section className="bg-white rounded-xl shadow p-6 space-y-8">
      <h2 className="text-lg font-semibold">검색 설정</h2>

      {/* 알림 설정 */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
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

      {/* 항공 정책 */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          항공 정책
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-center">
          <NumInput
            label="성인 수"
            value={value.adults}
            min={1}
            onChange={(v) => set("adults", v)}
          />
          <label className="flex items-center gap-2 mt-5">
            <input
              type="checkbox"
              checked={value.nonStop}
              onChange={(e) => set("nonStop", e.target.checked)}
              className="w-4 h-4"
            />
            <span className="text-sm text-gray-700">직항만</span>
          </label>
          <label className="flex items-center gap-2 mt-5">
            <input
              type="checkbox"
              checked={value.allow_mixed_airline}
              onChange={(e) => set("allow_mixed_airline", e.target.checked)}
              className="w-4 h-4"
            />
            <span className="text-sm text-gray-700">혼합 항공사 허용</span>
          </label>
        </div>
      </div>

      {/* 여행 일정 */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          여행 일정
        </h3>

        {/* stay_durations */}
        <div>
          <span className="text-sm text-gray-600 block mb-2">체류 일수</span>
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: 30 }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                onClick={() => toggleStay(n)}
                className={`w-8 h-8 rounded text-xs font-medium transition-colors ${
                  value.stay_durations.includes(n)
                    ? "bg-blue-500 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 수집 범위 */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          수집 범위
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <NumInput
            label="출발일 범위 (일)"
            value={value.departure_date_range_days}
            onChange={(v) => set("departure_date_range_days", v)}
          />
          <NumInput
            label="Amadeus 최대 요청 수"
            value={value.amadeus_max_requests_per_run}
            onChange={(v) => set("amadeus_max_requests_per_run", v)}
          />
        </div>
      </div>

      {/* LCC */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          LCC 설정
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
          <NumInput
            label="날짜별 Top-K"
            value={value.lcc_topk_per_date}
            onChange={(v) => set("lcc_topk_per_date", v)}
          />
          <div className="flex flex-col gap-1">
            <span className="text-sm text-gray-600">최대 수집 일수</span>
            <div className="flex items-center gap-3">
              <input
                type="number"
                min={1}
                value={value.lcc_max_days ?? ""}
                disabled={value.lcc_max_days === null}
                onChange={(e) => set("lcc_max_days", Number(e.target.value) || 1)}
                className="border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 w-24 disabled:bg-gray-100"
              />
              <label className="flex items-center gap-1 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={value.lcc_max_days === null}
                  onChange={(e) => set("lcc_max_days", e.target.checked ? null : 5)}
                  className="w-4 h-4"
                />
                전체
              </label>
            </div>
          </div>
          <NumInput
            label="요청 딜레이 (초)"
            value={value.request_delay}
            step={0.1}
            onChange={(v) => set("request_delay", v)}
          />
        </div>
      </div>
    </section>
  );
}
