export const DAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-05-01" → "05.01(목)" */
export function formatDate(d: string) {
  const parts = d.split("-");
  const dt = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  return `${parts[1]}.${parts[2]}(${DAY_NAMES[dt.getDay()]})`;
}

/** "AM 10:30" / "PM 3:10" → "10:30" / "15:10" */
export function normalizeTime(t: string | null) {
  if (!t) return "??:??";
  const m = t.match(/^(AM|PM)\s*(\d+):(\d+)/i);
  if (!m) return t.trim();
  let h = parseInt(m[2]);
  const min = m[3];
  if (m[1].toUpperCase() === "PM" && h !== 12) h += 12;
  if (m[1].toUpperCase() === "AM" && h === 12) h = 0;
  return `${String(h).padStart(2, "0")}:${min}`;
}

export function formatDuration(min: number | null) {
  if (min == null) return "-";
  return `${Math.floor(min / 60)}h ${min % 60}m`;
}

/** 수집이 지연됐다고 볼 임계 시간 (정상 주기 3h를 충분히 넘는 값) */
export const STALE_HOURS = 12;

/** ISO 시각 → 현재까지 경과 시간(시간 단위, 소수). 파싱 실패 시 Infinity. */
export function hoursSince(iso: string): number {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return Infinity;
  return (Date.now() - t) / 3_600_000;
}

/** ISO 시각 → "방금 전 / N분 전 / N시간 전 / N일 전" */
export function timeAgo(iso: string): string {
  const h = hoursSince(iso);
  if (!isFinite(h)) return "-";
  if (h < 1 / 60) return "방금 전";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}분 전`;
  if (h < 24) return `${Math.floor(h)}시간 전`;
  return `${Math.floor(h / 24)}일 전`;
}
