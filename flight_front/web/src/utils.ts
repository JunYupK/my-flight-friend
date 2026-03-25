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
