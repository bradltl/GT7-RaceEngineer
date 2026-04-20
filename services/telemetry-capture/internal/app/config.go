package app

import (
	"encoding/json"
	"fmt"
	"os"
)

type Config struct {
	TelemetryCapture struct {
		UDPListen      string `json:"udp_listen"`
		EngineerURL    string `json:"engineer_ingest_url"`
		RecordingDir   string `json:"recording_dir"`
		ReplaySpeedMS  int    `json:"replay_speed_ms"`
		SourceMode     string `json:"source_mode"`
	} `json:"telemetry_capture"`
}

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}
	if cfg.TelemetryCapture.RecordingDir == "" {
		cfg.TelemetryCapture.RecordingDir = "recordings"
	}
	if cfg.TelemetryCapture.ReplaySpeedMS == 0 {
		cfg.TelemetryCapture.ReplaySpeedMS = 1000
	}
	if cfg.TelemetryCapture.SourceMode == "" {
		cfg.TelemetryCapture.SourceMode = "replay"
	}
	return &cfg, nil
}

