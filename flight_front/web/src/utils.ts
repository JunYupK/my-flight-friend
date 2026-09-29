export const DAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-05-01" → "05.01(목)" */
export function formatDate(d: string) {
  const parts = d.split("-");
  const dt = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  return `${parts[1]}.${parts[2]}(${DAY_NAMES[dt.getDay()]})`;
}

export function formatDuration(min: number | null) {
  if (min == null) return "-";
  return `${Math.floor(min / 60)}h ${min % 60}m`;
}

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

/** 12345 → "12,345원" */
export function formatWon(n: number): string {
  return `${n.toLocaleString("ko-KR")}원`;
}
