import type { Stats } from "../../types";
import { formatWon, shortMd } from "../../utils";

function formatChange(pct: number): string {
  const sign = pct < 0 ? "−" : pct > 0 ? "+" : "";
  return `${sign}${Math.abs(pct).toFixed(1)}%`;
}

function Cell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-apple-secondary">{label}</div>
      <div className="font-semibold text-apple-text">{value}</div>
      {sub && <div className="text-xs text-apple-secondary">{sub}</div>}
    </div>
  );
}

export default function TrackingSummary({ stats }: { stats: Stats }) {
  if (stats.current == null) {
    return (
      <section className="rounded-2xl bg-apple-surface p-4 text-sm text-apple-secondary">
        확인가 없음 (오래된 관측만 있음)
      </section>
    );
  }
  if (!stats.comparable || stats.start == null || stats.low == null || stats.median == null) {
    return (
      <section className="rounded-2xl bg-apple-surface p-4">
        <div className="text-xs text-apple-secondary">현재</div>
        <div className="text-xl font-semibold text-apple-text">{formatWon(stats.current)}</div>
        <p className="mt-1 text-sm text-apple-secondary">추적 {stats.days}일째 · 비교 이력 수집 중</p>
      </section>
    );
  }
  const startMd = stats.start_day ? shortMd(stats.start_day) : "";
  const pct = stats.start > 0 ? ((stats.current - stats.start) / stats.start) * 100 : null;
  return (
    <section className="rounded-2xl bg-apple-surface p-4">
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Cell label="현재" value={formatWon(stats.current)} />
        <Cell label="추적 시작" value={formatWon(stats.start)} sub={startMd} />
        <Cell label="추적 이후 최저" value={formatWon(stats.low)} sub={stats.low_day ? shortMd(stats.low_day) : undefined} />
        <Cell label="중앙값" value={formatWon(stats.median)} />
      </div>
      {pct != null && (
        <p className="mt-3 text-sm text-apple-text">
          추적 시작({startMd}) 대비 <span className="font-semibold">{formatChange(pct)}</span>
        </p>
      )}
    </section>
  );
}
