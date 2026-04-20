package main

import (
	"flag"
	"log"
	"os"
	"path/filepath"

	"gt7race/telemetry-capture/internal/app"
)

func main() {
	var cfgPath string
	flag.StringVar(&cfgPath, "config", "../../config/default.json", "path to config json")
	flag.Parse()

	cfg, err := app.LoadConfig(cfgPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	if err := os.MkdirAll(filepath.Clean(cfg.TelemetryCapture.RecordingDir), 0o755); err != nil {
		log.Fatalf("prepare recordings dir: %v", err)
	}

	service := app.NewService(cfg)
	if err := service.Run(); err != nil {
		log.Fatalf("run telemetry capture: %v", err)
	}
}
