export interface Airport {
  code: string;
  city: string;
  name: string;
  country: string;
}

export const AIRPORTS: Airport[] = [
  // 일본
  { code: "NRT", city: "도쿄", name: "나리타 국제공항", country: "일본" },
  { code: "HND", city: "도쿄", name: "하네다 공항", country: "일본" },
  { code: "KIX", city: "오사카", name: "간사이 국제공항", country: "일본" },
  { code: "ITM", city: "오사카", name: "이타미 공항", country: "일본" },
  { code: "NGO", city: "나고야", name: "주부 국제공항", country: "일본" },
  { code: "FUK", city: "후쿠오카", name: "후쿠오카 공항", country: "일본" },
  { code: "CTS", city: "삿포로", name: "신치토세 공항", country: "일본" },
  { code: "OKA", city: "오키나와", name: "나하 공항", country: "일본" },
  { code: "KOJ", city: "가고시마", name: "가고시마 공항", country: "일본" },
  { code: "KMJ", city: "구마모토", name: "구마모토 공항", country: "일본" },
  { code: "NGS", city: "나가사키", name: "나가사키 공항", country: "일본" },
  { code: "OIT", city: "오이타", name: "오이타 공항", country: "일본" },
  { code: "KMI", city: "미야자키", name: "미야자키 공항", country: "일본" },
  { code: "HIJ", city: "히로시마", name: "히로시마 공항", country: "일본" },
  { code: "OKJ", city: "오카야마", name: "오카야마 공항", country: "일본" },
  { code: "TAK", city: "다카마쓰", name: "다카마쓰 공항", country: "일본" },
  { code: "MYJ", city: "마쓰야마", name: "마쓰야마 공항", country: "일본" },
  { code: "TKS", city: "도쿠시마", name: "도쿠시마 공항", country: "일본" },
  { code: "UBJ", city: "야마구치", name: "야마구치 우베 공항", country: "일본" },
  { code: "YGJ", city: "요나고", name: "요나고 공항", country: "일본" },
  { code: "TOY", city: "도야마", name: "도야마 공항", country: "일본" },
  { code: "KMQ", city: "고마쓰", name: "고마쓰 공항", country: "일본" },
  { code: "SDJ", city: "센다이", name: "센다이 공항", country: "일본" },
  { code: "AOJ", city: "아오모리", name: "아오모리 공항", country: "일본" },
  { code: "HKD", city: "하코다테", name: "하코다테 공항", country: "일본" },
  { code: "AKJ", city: "아사히카와", name: "아사히카와 공항", country: "일본" },
  { code: "KUH", city: "구시로", name: "구시로 공항", country: "일본" },
  { code: "MMB", city: "메만베쓰", name: "메만베쓰 공항", country: "일본" },
  { code: "GAJ", city: "야마가타", name: "야마가타 공항", country: "일본" },
  { code: "FSZ", city: "시즈오카", name: "시즈오카 공항", country: "일본" },
  { code: "KIJ", city: "니가타", name: "니가타 공항", country: "일본" },
  { code: "MMJ", city: "마쓰모토", name: "마쓰모토 공항", country: "일본" },
  { code: "IBR", city: "이바라키", name: "이바라키 공항", country: "일본" },
  { code: "ISG", city: "이시가키", name: "신이시가키 공항", country: "일본" },
  { code: "MMY", city: "미야코지마", name: "미야코 공항", country: "일본" },
  { code: "UKB", city: "고베", name: "고베 공항", country: "일본" },
  // 근거리
  { code: "ICN", city: "인천", name: "인천 국제공항", country: "한국" },
  { code: "GMP", city: "서울", name: "김포 국제공항", country: "한국" },
  { code: "TPE", city: "타이베이", name: "타오위안 국제공항", country: "대만" },
  { code: "HKG", city: "홍콩", name: "홍콩 국제공항", country: "홍콩" },
  { code: "BKK", city: "방콕", name: "수완나품 공항", country: "태국" },
  { code: "DAD", city: "다낭", name: "다낭 국제공항", country: "베트남" },
  { code: "SGN", city: "호찌민", name: "탄손낫 국제공항", country: "베트남" },
  { code: "MNL", city: "마닐라", name: "니노이 아키노 국제공항", country: "필리핀" },
  { code: "CEB", city: "세부", name: "막탄세부 국제공항", country: "필리핀" },
  { code: "SIN", city: "싱가포르", name: "창이 공항", country: "싱가포르" },
  { code: "PVG", city: "상하이", name: "푸둥 국제공항", country: "중국" },
];

const BY_CODE = new Map(AIRPORTS.map((a) => [a.code, a]));

export function cityName(code: string): string | null {
  return BY_CODE.get(code.toUpperCase())?.city ?? null;
}
