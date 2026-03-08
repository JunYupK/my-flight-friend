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
  japan_airports: Record<string, string>;
  tfs_templates: Record<string, string>;  // "ICN_TYO", "TYO_ICN" 형식
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
  min_price: number;
  last_checked_at: string;
  rank: number;
}

export interface DestinationGroup {
  destination: string;
  destination_name: string;
  deals: Deal[];
}
