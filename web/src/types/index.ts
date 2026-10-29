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
