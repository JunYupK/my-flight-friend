export interface SearchConfig {
  adults: number;
  currency: string;
  nonStop: boolean;
  target_price_krw: number;
  alert_cooldown_hours: number;
  alert_realert_drop_krw: number;
  allow_mixed_airline: boolean;
  stay_durations: number[];
  departure_date_range_days: number;
  amadeus_max_requests_per_run: number;
  search_months: string[];
  lcc_topk_per_date: number;
  lcc_max_days: number | null;
  request_delay: number;
}

export interface ConfigData {
  search_config: SearchConfig;
}

export interface Airport {
  code: string;
  name: string;
  tfs_out: string;
  tfs_in: string;
}

export interface RunStatus {
  status: "idle" | "running" | "done" | "error";
  output: string;
  pid: number | null;
}

export interface Deal {
  origin: string;
  destination: string;
  destination_name: string;
  departure_date: string;
  return_date: string;
  stay_nights: number;
  trip_type: string;
  source: string;
  out_airline: string;
  in_airline: string;
  is_mixed_airline: boolean;
  out_dep_time: string | null;
  out_arr_time: string | null;
  out_duration_min: number | null;
  out_stops: number | null;
  in_dep_time: string | null;
  in_arr_time: string | null;
  in_duration_min: number | null;
  in_stops: number | null;
  out_arr_airport: string | null;
  in_dep_airport: string | null;
  out_url: string | null;
  in_url: string | null;
  out_price: number | null;
  in_price: number | null;
  min_price: number;
  last_checked_at: string;
  rank: number;
}

export interface DestinationGroup {
  destination: string;
  destination_name: string;
  top_deals: Deal[];
  diverse_deals: Deal[];
  min_price: number;
  total_count: number;
}

export interface PriceHistoryPoint {
  departure_date?: string;  // calendar 모드
  check_date?: string;      // timeline 모드
  source: string;
  min_price: number;
}

export interface PriceHistoryResponse {
  mode: "calendar" | "timeline";
  data: PriceHistoryPoint[];
}

export interface CollectionRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "partial" | "error";
  fsc_count: number;
  google_count: number;
  total_saved: number;
  alerts_sent: number;
  has_error: boolean;
  duration_sec: number | null;
  error_log?: string | null;
}
