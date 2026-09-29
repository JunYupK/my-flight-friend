// Task 11 API 응답 형태 그대로. 시각은 오프셋 포함 ISO 문자열 — new Date()로 파싱할 것.

export interface Preferences {
  out_dep_window: [string, string] | null;
  in_dep_window: [string, string] | null;
  nonstop_only: boolean;
  include_airlines: string[];
  exclude_airlines: string[];
  max_price: number | null;
  max_duration_min: number | null;
}

export interface TripSummary {
  id: number;
  destination: string;
  out_date: string;
  ret_date: string;
  days_to_departure: number;
  tracking: boolean;
  current: number | null;
  current_observed_at: string | null;
  change_vs_start_pct: number | null;
  archived: boolean;
}

export interface TripInfo {
  id: number;
  origin: string;
  destination: string;
  out_date: string;
  ret_date: string;
  adults: number;
  cabin: string;
  prefs: Preferences;
  target_price: number | null;
  tracking: boolean;
  archived: boolean;
  days_to_departure: number;
  created_at: string;
}

export interface ProviderPriceView {
  provider: string;
  price: number | null;
  observed_at: string;
  booking_url: string | null;
  stale: boolean;
}

export interface MergedLegView {
  flight_key: string;
  dep_time: string | null;
  arr_time: string | null;
  airline_name: string | null;
  airline_iata: string | null;
  flight_numbers: string[];
  stops: number | null;
  duration_min: number | null;
  dep_airport: string | null;
  arr_airport: string | null;
  best_price: number | null;
  best_provider: string | null;
  in_condition: boolean;
  violations: string[];
  prices: ProviderPriceView[];
}

export interface CandidateView {
  out_flight_key: string;
  in_flight_key: string;
  price: number;
  stay_min: number;
}

export interface NearMissView {
  direction: string;
  flight_key: string;
  violated: string[];
  combo_price: number | null;
  saving: number | null;
}

export interface RtReference {
  airline_iata: string;
  rt_min: number;
  ow_sum: number;
  diff: number;
}

export interface Stats {
  current: number | null;
  start: number | null;
  start_day: string | null;
  low: number | null;
  low_day: string | null;
  median: number | null;
  days: number;
  comparable: boolean;
}

export interface DayPoint {
  day: string;
  combo: number | null;
  out_min: number | null;
  in_min: number | null;
  partial: boolean;
}

export interface ProviderStatus {
  provider: string;
  status: string;
  observed_at: string;
  last_ok_at: string | null;
}

export interface RunSummary {
  id: number;
  status: string;
  requested_at: string;
}

export interface TripView {
  trip: TripInfo;
  run: RunSummary | null;
  providers: ProviderStatus[];
  stats: Stats;
  legs: { out: MergedLegView[]; in: MergedLegView[] };
  candidates: CandidateView[];
  near_miss: NearMissView | null;
  rt_reference: RtReference[];
  window_minutes: number;
}

export interface RunSnapshotStatus {
  provider: string;
  kind: string;
  direction: string | null;
  status: string;
}

export interface RunStatus {
  id: number;
  status: string;
  snapshots: RunSnapshotStatus[];
}

export interface TripCreateInput {
  destination: string;
  out_date: string;
  ret_date: string;
  prefs: Preferences;
  target_price: number | null;
}

export interface TripPatchInput {
  prefs?: Preferences;
  tracking?: boolean;
  target_price?: number | null;
}

export type StartRunResult =
  | { kind: "started"; runId: number }
  | { kind: "cooldown"; cooldownSeconds: number };

// Admin 응답은 서버가 repo dict를 그대로 내려준다 (Task 15에서 구체화).
export type AdminRow = Record<string, string | number | boolean | null>;
