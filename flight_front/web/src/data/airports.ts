import raw from "./airports.json";

export interface Airport {
  code: string;
  city: string;
  name: string;
  country: string;
  cityEn: string;
}

/** Naver 기준 한국어 이름이 있는 정기편 공항 (scripts/gen_airports.py로 생성). */
export const AIRPORTS: Airport[] = raw.map(([code = "", city = "", name = "", country = "", cityEn = ""]) => ({
  code,
  city,
  name,
  country,
  cityEn,
}));

const BY_CODE = new Map(AIRPORTS.map((a) => [a.code, a]));

/** 검색어가 없을 때 보여줄 인기 여행지 (순서 유지). */
const POPULAR_CODES = [
  "NRT", "HND", "KIX", "ITM", "NGO", "FUK", "CTS", "OKA", "KOJ", "KMJ",
  "NGS", "OIT", "KMI", "HIJ", "OKJ", "TAK", "MYJ", "TKS", "UBJ", "YGJ",
  "TOY", "KMQ", "SDJ", "AOJ", "HKD", "AKJ", "KUH", "MMB", "GAJ", "FSZ",
  "KIJ", "MMJ", "IBR", "ISG", "MMY", "UKB", "TPE", "HKG", "BKK", "DAD",
  "CXR", "PQC", "SGN", "MNL", "CEB", "DPS", "CNX", "SIN", "PVG", "GMP",
];

export const POPULAR: Airport[] = POPULAR_CODES.flatMap((c) => BY_CODE.get(c) ?? []);

export function findAirport(code: string): Airport | null {
  return BY_CODE.get(code.toUpperCase()) ?? null;
}

export function cityName(code: string): string | null {
  return findAirport(code)?.city ?? null;
}

/** 코드 일치 → 도시명 시작 → 영문 도시명 시작 → 어디든 포함 순으로 상위 limit개. */
export function searchAirports(query: string, limit = 50): Airport[] {
  const q = query.trim().toLowerCase();
  if (!q) return POPULAR;
  const ranked: [number, Airport][] = [];
  for (const a of AIRPORTS) {
    const city = a.city.toLowerCase();
    const cityEn = a.cityEn.toLowerCase();
    let rank: number;
    if (a.code.toLowerCase() === q) rank = 0;
    else if (city.startsWith(q)) rank = 1;
    else if (cityEn.startsWith(q)) rank = 2;
    else if (`${a.code} ${city} ${a.name} ${a.country} ${cityEn}`.toLowerCase().includes(q)) rank = 3;
    else continue;
    ranked.push([rank, a]);
  }
  return ranked
    .sort((x, y) => x[0] - y[0] || x[1].city.localeCompare(y[1].city, "ko") || x[1].code.localeCompare(y[1].code))
    .slice(0, limit)
    .map(([, a]) => a);
}
