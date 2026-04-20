export type Priority = 'critical' | 'warning' | 'info'
export type ConnectionState = 'connected' | 'degraded' | 'disconnected' | 'unknown'
export type SourceMode = 'live' | 'replay' | 'mock' | 'unknown'

export interface EngineerMessage {
  id: string
  timestamp_ms: number
  priority: Priority
  category: string
  text: string
  ttl_ms: number
  source_event_id?: string | null
  suppressed?: boolean
  suppression_reason?: string | null
}

export interface SessionMetrics {
  session_id?: string | null
  track_name?: string | null
  lap_number?: number | null
  laps_remaining?: number | null
  lap_time_ms?: number | null
  last_lap_time_ms?: number | null
  best_lap_time_ms?: number | null
  fuel_liters?: number | null
  fuel_laps_remaining_estimate?: number | null
  projected_fuel_to_finish_liters?: number | null
  connection_state: ConnectionState
  source_mode: SourceMode
  stale_ms?: number | null
}

export interface DashboardState {
  latest_message: EngineerMessage | null
  recent_messages: EngineerMessage[]
  metrics: SessionMetrics
}

