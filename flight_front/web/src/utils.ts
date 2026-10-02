export const DAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-05-01" → "05.01(목)" */
export function formatDate(d: string) {
  const parts = d.split("-");
  const dt = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  return `${parts[1]}.${parts[2]}(${DAY_NAMES[dt.getDay()]})`;
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

/** 다음 자동 확인 시각 → "HH:MM" (지났으면 "곧", 오늘 이후 날짜면 "내일 HH:MM"). 브라우저 로컬 시각 기준. */
export function nextAutoLabel(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "-";
  if (d.getTime() <= now.getTime()) return "곧";
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  return day(d) > day(now) ? `내일 ${hm}` : hm;
}

/** 12345 → "12,345원" */
export function formatWon(n: number): string {
  return `${n.toLocaleString("ko-KR")}원`;
}

/** "2026-10-21" → "10/21" */
export function shortMd(d: string): string {
  return `${parseInt(d.slice(5, 7), 10)}/${parseInt(d.slice(8, 10), 10)}`;
}

/** ISO 시각 → "10/2 14:05" (브라우저 로컬 시간). */
export function mdHm(iso: string | number): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** ISO 시각 또는 epoch ms → "10/2" (브라우저 로컬 날짜). */
export function md(iso: string | number): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function dday(n: number): string {
  if (n === 0) return "D-day";
  return n > 0 ? `D-${n}` : `D+${-n}`;
}

function utcDay(d: string): number {
  return Date.UTC(parseInt(d.slice(0, 4), 10), parseInt(d.slice(5, 7), 10) - 1, parseInt(d.slice(8, 10), 10));
}

/** 두 "YYYY-MM-DD" 사이 박 수. */
export function nightsBetween(outDate: string, retDate: string): number {
  return Math.round((utcDay(retDate) - utcDay(outDate)) / 86_400_000);
}

function hhmmToMin(t: string): number {
  return parseInt(t.slice(0, 2), 10) * 60 + parseInt(t.slice(3, 5), 10);
}

/** 출국편 도착(arr < dep면 +1일)부터 귀국편 출발까지의 분 (현지 시각 기준, 백엔드 stay_minutes와 같은 규칙). */
export function stayMinutes(outDate: string, outDep: string, outArr: string, retDate: string, retDep: string): number {
  const dayDiff = Math.round((utcDay(retDate) - utcDay(outDate)) / 86_400_000);
  const overnight = outArr < outDep ? 1 : 0;
  return (dayDiff - overnight) * 1440 + hhmmToMin(retDep) - hhmmToMin(outArr);
}

/** 분 → "2일 3시간" / "5시간 30분" */
export function formatStay(min: number): string {
  const sign = min < 0 ? "-" : "";
  const a = Math.abs(min);
  const d = Math.floor(a / 1440);
  const h = Math.floor((a % 1440) / 60);
  const m = a % 60;
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}일`);
  if (h > 0 || (d === 0 && m === 0)) parts.push(`${h}시간`);
  if (d === 0 && m > 0) parts.push(`${m}분`);
  return sign + parts.join(" ");
}

export function minutesToHHMM(m: number): string {
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function hhmmToMinutes(s: string): number {
  return hhmmToMin(s);
}

/** 백엔드 시간대(["HH:MM","HH:MM"] | null) → 슬라이더 분 값. null·"23:59"는 전체/끝(1440). */
export function windowToSlider(v: [string, string] | null): [number, number] {
  if (!v) return [0, 1440];
  return [hhmmToMinutes(v[0]), v[1] === "23:59" ? 1440 : hhmmToMinutes(v[1])];
}

/** 슬라이더 분 값 → 백엔드 시간대. [0,1440]은 제한 없음(null), 끝 1440은 "23:59". */
export function sliderToWindow([a, b]: [number, number]): [string, string] | null {
  if (a === 0 && b === 1440) return null;
  return [minutesToHHMM(a), b === 1440 ? "23:59" : minutesToHHMM(b)];
}
