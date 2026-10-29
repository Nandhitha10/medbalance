export type FacilityType = "Hospital" | "DH" | "TH" | "CHC" | "PHC" | "Warehouse";

export interface Facility {
  id: string;
  name: string;
  facility_type: FacilityType | string;
  latitude: number;
  longitude: number;
  cold_storage_available: boolean;
  min_reserve_days: number;
  health_status?: "healthy" | "warning" | "critical";
  shortage_count?: number;
}

export interface Drug {
  code: string;
  name: string;
  category: "V" | "E" | "N" | string;
  unit: string;
  pack_size: number;
  cold_chain?: boolean;
  storage_condition?: string;
  min_temp_c?: number | null;
  max_temp_c?: number | null;
  unit_cost_inr: number;
  min_residual_days: number;
  is_controlled?: boolean;
}

export interface Lot {
  id?: number | null;
  facility_id: string;
  drug_code: string;
  batch_no: string;
  expiry: string;
  quantity: number;
  created_at?: string | null;
}

export interface Position {
  facility_id: string;
  drug_code: string;
  stock_on_hand: number;
  effective_stock: number;
  at_risk_stock: number;
  reserve: number;
  shortage: number;
  daily_consumption_rate: number;
}

export interface TransferOrder {
  id: string;
  plan_id?: string;
  source_facility_id: string;
  destination_facility_id: string;
  drug_code: string;
  batch_no: string;
  lot_quantity?: number;
  quantity: number;
  usable_quantity: number;
  status: "DRAFT" | "APPROVED" | "IN_TRANSIT" | "DELIVERED" | "CANCELLED";
  temperature_controlled: boolean;
  savings_inr?: number;
  created_at?: string;
  updated_at?: string;
}

export interface PlanRun {
  id: string;
  timestamp: string;
  status: string;
  mode?: string;
  solver_tier?: string;
  execution_time_sec?: number;
  total_orders: number;
  total_units: number;
  shortage_reduction: number;
  expiry_avoided: number;
  total_savings_inr: number;
  orders: TransferOrder[];
  waste_moved_units?: number;
  trips?: number;
  violations_count?: number;
  qcloud_tier?: string;
  solver_meta?: Record<string, any>;
  summary?: Record<string, any>;
}

export interface ClockState {
  now: string;
  today: string;
  is_running: boolean;
  speed: number;
  day_index?: number;
}

export interface SSEEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  data: Record<string, any>;
}

export type NavPage =
  | "map"
  | "ingestion"
  | "plan"
  | "benchmark"
  | "coldchain"
  | "results"
  | "ai-health"
  | "scenarios";

export interface ExtractionItem {
  id: string;
  report_id: string;
  raw_text: string;
  drug_code?: string;
  batch_no?: string;
  expiry?: string;
  quantity?: number;
  confidence?: number;
  is_anomalous?: boolean;
  anomaly_reason?: string;
  anomaly_type?: string;
  review_status?: string;
  suggested_patch?: {
    drug_code?: string;
    batch_no?: string;
    expiry?: string;
    quantity?: number;
  };
}

export interface StockReport {
  id: string;
  facility_code: string;
  received_at: string;
  status: "RECEIVED" | "PROCESSING" | "PROCESSED" | "NEEDS_REVIEW" | "RESOLVED" | string;
  source_type: "fhir" | "csv" | "excel" | "chat" | "text" | "pdf" | string;
  language?: string;
  extracted_items_count: number;
  anomalies_detected: number;
  raw_content?: string;
  items?: ExtractionItem[];
}

export interface PolicyBenchmarkRow {
  policy: string;
  objective_value: number;
  shortage_reduction: number;
  expiry_avoided_inr: number;
  waste_moved: number;
  trips: number;
  runtime_sec: number;
}

export interface ZoningBenchmark {
  num_nodes: number;
  num_edges: number;
  maxcut: {
    cut_value: number;
    intra_zone_weight: number;
    tier: string;
    runtime_sec: number;
  };
  kmeans: {
    cut_value: number;
    intra_zone_weight: number;
    runtime_sec: number;
  };
  exact_cut_value?: number;
  improvement_percent: number;
  partition: Record<string, number>;
}

export interface BenchmarkData {
  plan_id: string;
  solver_tier: string;
  milp_optimal_energy: number;
  solver_energy: number;
  optimality_gap_percent: number;
  solver_time_sec: number;
  milp_time_sec: number;
  comparison_table: PolicyBenchmarkRow[];
  zoning?: ZoningBenchmark;
}

export interface ColdchainDevice {
  device_id: string;
  assigned_to: string;
  name?: string;
  type?: "vehicle" | "facility";
  latest_temp_c: number;
  battery_percent: number;
  last_ping: string;
  status: "OK" | "WARNING" | "EXCURSION" | "RECOVERED" | "OFFLINE" | string;
  door_open?: boolean;
  target_name?: string;
  min_allowed_c?: number;
  max_allowed_c?: number;
  telemetry?: {
    timestamp: string;
    temperature_c: number;
  }[];
}

export interface ScenarioItem {
  id: string;
  name: string;
  title?: string;
  desc: string;
  active: boolean;
  fault_active?: boolean;
}

export interface SignalItem {
  id: string;
  type: string;
  title: string;
  facility_id?: string;
  drug_code?: string;
  multiplier?: number;
  start_date?: string;
  end_date?: string;
  status: string;
  timestamp?: string;
  reason?: string;
}
