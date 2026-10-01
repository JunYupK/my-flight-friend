export interface ProviderMeta {
  label: string;
  initial: string;
  colorVar: string;
}

export const PROVIDERS: Record<string, ProviderMeta> = {
  google_flights: { label: "Google Flights", initial: "G", colorVar: "--provider-google_flights" },
  naver: { label: "Naver", initial: "N", colorVar: "--provider-naver" },
};

/** 모르는 제공자는 회색 + 이름 첫 글자 대문자. */
export function providerMeta(id: string): ProviderMeta {
  return (
    PROVIDERS[id] ?? {
      label: id,
      initial: (id.charAt(0) || "?").toUpperCase(),
      colorVar: "--muted-foreground",
    }
  );
}

export function providerLabel(id: string): string {
  return providerMeta(id).label;
}

export const STATUS_REASON: Record<string, string> = {
  blocked: "차단 의심",
  empty: "결과 없음",
  error: "오류",
};
