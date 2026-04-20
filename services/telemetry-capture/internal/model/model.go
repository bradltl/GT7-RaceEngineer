package model

// TelemetrySnapshot is the normalized contract shared with the engineer service.
// TODO(gt7-field-validation): confirm each optional field against live GT7 packets.
type TelemetrySnapshot struct {
	EventID                       string             `json:"event_id"`
	TimestampMS                   int64              `json:"timestamp_ms"`
	SessionID                     string             `json:"session_id"`
	Source                        string             `json:"source"`
	SourceMode                    string             `json:"source_mode"`
	ConnectionState               string             `json:"connection_state"`
	TrackName                     string             `json:"track_name,omitempty"`
	SessionType                   string             `json:"session_type,omitempty"`
	LapNumber                     int                `json:"lap_number,omitempty"`
	LapsTotal                     *int               `json:"laps_total,omitempty"`
	LapsRemaining                 *int               `json:"laps_remaining,omitempty"`
	LapTimeMS                     *int               `json:"lap_time_ms,omitempty"`
	LastLapTimeMS                 *int               `json:"last_lap_time_ms,omitempty"`
	BestLapTimeMS                 *int               `json:"best_lap_time_ms,omitempty"`
	FuelLiters                    *float64           `json:"fuel_liters,omitempty"`
	FuelCapacityLiters            *float64           `json:"fuel_capacity_liters,omitempty"`
	FuelLapsRemainingEstimate     *float64           `json:"fuel_laps_remaining_estimate,omitempty"`
	ProjectedFuelToFinishLiters   *float64           `json:"projected_fuel_to_finish_liters,omitempty"`
	TireWearPct                   *float64           `json:"tire_wear_pct,omitempty"`
	SpeedKPH                      *float64           `json:"speed_kph,omitempty"`
	ThrottlePct                   *float64           `json:"throttle_pct,omitempty"`
	BrakePct                      *float64           `json:"brake_pct,omitempty"`
	Gear                          *int               `json:"gear,omitempty"`
	RPM                           *int               `json:"rpm,omitempty"`
	Flags                         map[string]bool    `json:"flags,omitempty"`
	Weather                       map[string]float64 `json:"weather,omitempty"`
	Derived                       map[string]float64 `json:"derived,omitempty"`
	Raw                           map[string]any     `json:"raw,omitempty"`
	ValidationWarnings            []string           `json:"validation_warnings,omitempty"`
}

type CaptureHealth struct {
	Mode             string `json:"mode"`
	LastEventID      string `json:"last_event_id,omitempty"`
	LastTimestampMS  int64  `json:"last_timestamp_ms,omitempty"`
	EventsRecorded   int64  `json:"events_recorded"`
	LastForwardError string `json:"last_forward_error,omitempty"`
}

// RawPacket preserves live UDP traffic for later decoder work.
// TODO(gt7-field-validation): define the decoded packet contract once packet structure is validated.
type RawPacket struct {
	TimestampMS   int64  `json:"timestamp_ms"`
	RemoteAddr    string `json:"remote_addr"`
	SourceMode    string `json:"source_mode"`
	PayloadBase64  string `json:"payload_base64"`
	ValidationNote string `json:"validation_note,omitempty"`
}
