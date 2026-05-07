// ── Auth ─────────────────────────────────────────────────────────────────────
export type UserRole = 'admin' | 'police' | 'analyst' | 'readonly'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  badge_number: string | null
  department: string | null
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user_id: string
  role: UserRole
  full_name: string
}

// ── Crime ─────────────────────────────────────────────────────────────────────
export type CrimeStatus = 'reported' | 'under_investigation' | 'resolved' | 'closed'
export type CrimeSeverity = 1 | 2 | 3 | 4 | 5

export interface Crime {
  id: string
  crime_type: string
  sub_type: string | null
  description: string | null
  severity: CrimeSeverity
  location_name: string | null
  address: string | null
  district: string | null
  city: string
  latitude: number
  longitude: number
  occurred_at: string
  reported_at: string
  status: CrimeStatus
  case_number: string | null
  assigned_officer_id: string | null
  cluster_id: number | null
  risk_score: number | null
  created_at: string
  updated_at: string
}

export interface CrimeListResponse {
  items: Crime[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface CrimeStats {
  total_crimes: number
  by_type: Record<string, number>
  by_district: Record<string, number>
  by_status: Record<string, number>
  by_severity: Record<string, number>
  by_month: Array<{ year: number; month: number; count: number }>
  avg_daily_crimes: number
  most_active_hour: number
}

export interface CrimeCreatePayload {
  crime_type: string
  sub_type?: string
  description?: string
  severity: number
  latitude: number
  longitude: number
  location_name?: string
  address?: string
  district?: string
  city: string
  occurred_at: string
  status?: CrimeStatus
  case_number?: string
}

export interface HeatmapPoint {
  lat: number
  lng: number
  weight: number
}

export interface HotspotData {
  district: string
  crime_type: string
  count: number
  lat: number
  lng: number
  max_severity: number
}

// ── GeoJSON ───────────────────────────────────────────────────────────────────
export interface GeoJSONFeatureCollection {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    geometry: { type: 'Point'; coordinates: [number, number] }
    properties: {
      id: string
      crime_type: string
      severity: number
      district: string | null
      status: string
      occurred_at: string
      risk_score: number | null
    }
  }>
  metadata: Record<string, unknown>
}

// ── Alerts ────────────────────────────────────────────────────────────────────
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type AlertType = 'hotspot' | 'cluster' | 'high_risk' | 'pattern' | 'system' | 'manual'

export interface Alert {
  id: string
  title: string
  message: string
  alert_type: AlertType
  severity: AlertSeverity
  is_read: boolean
  is_resolved: boolean
  latitude: number | null
  longitude: number | null
  district: string | null
  related_crime_id: string | null
  target_role: string | null
  created_at: string
  updated_at: string
}

export interface AlertListResponse {
  items: Alert[]
  total: number
  unread_count: number
}

// ── FIR ───────────────────────────────────────────────────────────────────────
export interface FIRReport {
  id: string
  fir_number: string
  crime_id: string | null
  submitted_by: string
  raw_text: string
  file_url: string | null
  extracted_entities: ExtractedEntities | null
  extraction_confidence: number | null
  nlp_status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  updated_at: string
}

export interface ExtractedEntities {
  locations: string[]
  primary_location: string | null
  crime_type: string | null
  crime_type_confidence: number
  weapons: string[]
  suspects: SuspectDescription[]
  time_references: string[]
  ipc_sections: string[]
  overall_confidence: number
  inferred_severity: number
  has_weapon: boolean
  has_injury: boolean
}

export interface SuspectDescription {
  raw_description: string
  age?: string
  gender?: 'male' | 'female'
  build?: string
  complexion?: string
  clothing?: string[]
}

// ── ML ────────────────────────────────────────────────────────────────────────
export interface ClusterSummary {
  cluster_id: number
  size: number
  centroid_lat: number
  centroid_lng: number
  dominant_crime_type: string
  crime_type_breakdown: Record<string, number>
  avg_severity: number
  bbox: { min_lat: number; max_lat: number; min_lng: number; max_lng: number }
}

export interface ClusterResult {
  status: string
  num_clusters: number
  noise_points: number
  total_points: number
  coverage_pct: number
  parameters: { eps_km: number; min_samples: number }
  clusters: ClusterSummary[]
  from_cache?: boolean
}

export interface RiskScore {
  score: number
  level: 'low' | 'medium' | 'high' | 'critical'
  components: {
    total_crimes: number
    recent_7d: number
    recent_30d: number
    avg_severity: number
    max_severity: number
  }
}

export interface HotspotPrediction {
  district: string
  hotspot_probability: number
  is_hotspot: boolean
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  predicted_for: string
}

// ── Patrol ────────────────────────────────────────────────────────────────────
export interface PatrolStop {
  stop_number: number
  node_id: string
  label: string
  lat: number
  lng: number
  risk_score: number
  crime_count: number
  node_type: string
  distance_from_prev_km: number
  cumulative_distance_km: number
}

export interface PatrolRoute {
  route_id: string
  strategy: string
  district: string
  checkpoints: PatrolStop[]
  total_distance_km: number
  estimated_duration_minutes: number
  total_risk_covered: number
  coverage_radius_km: number
  generated_at: string
  from_cache?: boolean
}

// ── Simulation ────────────────────────────────────────────────────────────────
export interface SimulationResult {
  simulation_id: string
  scenario: string
  district: string
  parameters: Record<string, unknown>
  num_simulations: number
  baseline: {
    crimes_per_day: number
    by_type: Record<string, number>
    risk_level: string
  }
  projected: {
    crimes_per_day: number
    by_type: Record<string, number>
    risk_level: string
  }
  reduction: {
    mean_pct: number
    std_pct: number
    p5_pct: number
    p50_pct: number
    p95_pct: number
    confidence_interval_95: [number, number]
  }
  simulated_at: string
}

// ── Pagination ────────────────────────────────────────────────────────────────
export interface PaginationParams {
  limit?: number
  offset?: number
}

// ── API error ─────────────────────────────────────────────────────────────────
export interface APIError {
  error: string
  message: string
  path: string
  detail?: unknown
}

// ── WebSocket messages ────────────────────────────────────────────────────────
export type WSMessage =
  | { type: 'connected'; user_id: string; role: string; message: string }
  | { type: 'new_alert'; alert_id: string; severity: AlertSeverity; title: string }
  | { type: 'ping' }
  | { type: 'pong' }
