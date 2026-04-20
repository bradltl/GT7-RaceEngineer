package app

import (
	"bufio"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"gt7race/telemetry-capture/internal/model"
)

type Service struct {
	cfg    *Config
	mu     sync.RWMutex
	health model.CaptureHealth
	latest model.TelemetrySnapshot
	events []model.TelemetrySnapshot
}

func NewService(cfg *Config) *Service {
	return &Service{
		cfg: cfg,
		health: model.CaptureHealth{
			Mode: cfg.TelemetryCapture.SourceMode,
		},
	}
}

func (s *Service) Run() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", s.healthHandler)
	mux.HandleFunc("/state", s.stateHandler)
	mux.HandleFunc("/events", s.eventsHandler)
	mux.HandleFunc("/record", s.recordHandler)

	server := &http.Server{
		Addr:    ":8090",
		Handler: mux,
	}

	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("telemetry capture http server: %v", err)
		}
	}()

	switch strings.ToLower(s.cfg.TelemetryCapture.SourceMode) {
	case "mock":
		go s.runMock()
	case "replay":
		go s.runReplay()
	case "live":
		go s.runLiveUDP()
	default:
		return fmt.Errorf("unknown source mode %q", s.cfg.TelemetryCapture.SourceMode)
	}

	select {}
}

func (s *Service) healthHandler(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	writeJSON(w, s.health)
}

func (s *Service) stateHandler(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	writeJSON(w, s.latest)
}

func (s *Service) eventsHandler(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	writeJSON(w, s.events)
}

func (s *Service) recordHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	var input struct {
		Path string `json:"path"`
	}
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if input.Path == "" {
		http.Error(w, "path is required", http.StatusBadRequest)
		return
	}
	go s.runReplayFile(input.Path)
	writeJSON(w, map[string]string{"status": "started"})
}

func (s *Service) runReplay() {
	path := filepath.Clean(filepath.Join("..", "..", "contracts", "sample_normalized_telemetry.jsonl"))
	s.runReplayFile(path)
}

func (s *Service) runReplayFile(path string) {
	file, err := os.Open(path)
	if err != nil {
		s.setForwardError(fmt.Sprintf("open replay: %v", err))
		return
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Bytes()
		var snapshot model.TelemetrySnapshot
		if err := json.Unmarshal(line, &snapshot); err != nil {
			s.setForwardError(fmt.Sprintf("decode replay line: %v", err))
			continue
		}
		s.ingest(snapshot)
		time.Sleep(time.Duration(s.cfg.TelemetryCapture.ReplaySpeedMS) * time.Millisecond)
	}
	if err := scanner.Err(); err != nil {
		s.setForwardError(fmt.Sprintf("scan replay: %v", err))
	}
}

func (s *Service) runMock() {
	base := time.Now().UnixMilli()
	for i, snapshot := range mockSnapshots(base) {
		snapshot.TimestampMS = time.Now().UnixMilli() + int64(i*250)
		s.ingest(snapshot)
		time.Sleep(1 * time.Second)
	}
}

func (s *Service) runLiveUDP() {
	addr, err := net.ResolveUDPAddr("udp", s.cfg.TelemetryCapture.UDPListen)
	if err != nil {
		s.setForwardError(fmt.Sprintf("resolve udp: %v", err))
		return
	}
	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		s.setForwardError(fmt.Sprintf("listen udp: %v", err))
		return
	}
	defer conn.Close()

	buf := make([]byte, 4096)
	for {
		n, remote, err := conn.ReadFromUDP(buf)
		if err != nil {
			s.setForwardError(fmt.Sprintf("read udp: %v", err))
			continue
		}

		// TODO(gt7-field-validation): decode the encrypted GT7 payload here.
		// For now we persist the raw packet shape so the capture path exists
		// without pretending the live normalization is solved.
		if err := s.recordRawPacket(remote.String(), buf[:n]); err != nil {
			s.setForwardError(fmt.Sprintf("record raw packet: %v", err))
		}
		s.mu.Lock()
		s.health.EventsRecorded++
		s.health.LastTimestampMS = time.Now().UnixMilli()
		s.health.LastEventID = fmt.Sprintf("raw-%s-%d", remote.String(), s.health.EventsRecorded)
		s.mu.Unlock()
	}
}

func (s *Service) recordRawPacket(remoteAddr string, payload []byte) error {
	rawPath := filepath.Join(s.cfg.TelemetryCapture.RecordingDir, "raw-packets.jsonl")
	file, err := os.OpenFile(rawPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("open raw packet recording: %w", err)
	}
	defer file.Close()
	packet := model.RawPacket{
		TimestampMS:  time.Now().UnixMilli(),
		RemoteAddr:   remoteAddr,
		SourceMode:   "live",
		PayloadBase64: base64.StdEncoding.EncodeToString(payload),
		ValidationNote: "raw live GT7 UDP payload retained before decoder validation",
	}
	encoded, err := json.Marshal(packet)
	if err != nil {
		return fmt.Errorf("encode raw packet: %w", err)
	}
	if _, err := file.Write(append(encoded, '\n')); err != nil {
		return fmt.Errorf("write raw packet: %w", err)
	}
	return nil
}

func (s *Service) ingest(snapshot model.TelemetrySnapshot) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.latest = snapshot
	s.events = append(s.events, snapshot)
	if len(s.events) > 100 {
		s.events = s.events[len(s.events)-100:]
	}
	s.health.LastEventID = snapshot.EventID
	s.health.LastTimestampMS = snapshot.TimestampMS
	s.health.EventsRecorded++
	s.health.LastForwardError = ""
	if err := s.recordSnapshot(snapshot); err != nil {
		s.health.LastForwardError = err.Error()
	}
	if err := s.forwardSnapshot(snapshot); err != nil {
		s.health.LastForwardError = err.Error()
	}
}

func (s *Service) recordSnapshot(snapshot model.TelemetrySnapshot) error {
	recordingPath := filepath.Join(s.cfg.TelemetryCapture.RecordingDir, "session-recording.jsonl")
	file, err := os.OpenFile(recordingPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("open recording: %w", err)
	}
	defer file.Close()
	encoded, err := json.Marshal(snapshot)
	if err != nil {
		return fmt.Errorf("encode recording: %w", err)
	}
	if _, err := file.Write(append(encoded, '\n')); err != nil {
		return fmt.Errorf("write recording: %w", err)
	}
	return nil
}

func (s *Service) forwardSnapshot(snapshot model.TelemetrySnapshot) error {
	if s.cfg.TelemetryCapture.EngineerURL == "" {
		return nil
	}
	payload, err := json.Marshal(snapshot)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.cfg.TelemetryCapture.EngineerURL, strings.NewReader(string(payload)))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("forward status: %s", resp.Status)
	}
	return nil
}

func (s *Service) setForwardError(msg string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.health.LastForwardError = msg
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	_ = enc.Encode(v)
}

func mockSnapshots(base int64) []model.TelemetrySnapshot {
	intPtr := func(v int) *int { return &v }
	floatPtr := func(v float64) *float64 { return &v }
	return []model.TelemetrySnapshot{
		{EventID: "mock-1", TimestampMS: base, SessionID: "mock-session", Source: "mock", SourceMode: "mock", ConnectionState: "connected", TrackName: "Trial Mountain", SessionType: "race", LapNumber: 10, LapsTotal: intPtr(15), LapsRemaining: intPtr(5), LapTimeMS: intPtr(91240), LastLapTimeMS: intPtr(91810), BestLapTimeMS: intPtr(90780), FuelLiters: floatPtr(11.8), FuelLapsRemainingEstimate: floatPtr(5.8), ProjectedFuelToFinishLiters: floatPtr(1.6)},
		{EventID: "mock-2", TimestampMS: base + 1000, SessionID: "mock-session", Source: "mock", SourceMode: "mock", ConnectionState: "connected", TrackName: "Trial Mountain", SessionType: "race", LapNumber: 12, LapsTotal: intPtr(15), LapsRemaining: intPtr(3), LapTimeMS: intPtr(90850), LastLapTimeMS: intPtr(91020), BestLapTimeMS: intPtr(90780), FuelLiters: floatPtr(8.1), FuelLapsRemainingEstimate: floatPtr(3.9), ProjectedFuelToFinishLiters: floatPtr(0.9)},
		{EventID: "mock-3", TimestampMS: base + 2000, SessionID: "mock-session", Source: "mock", SourceMode: "mock", ConnectionState: "connected", TrackName: "Trial Mountain", SessionType: "race", LapNumber: 13, LapsTotal: intPtr(15), LapsRemaining: intPtr(2), LapTimeMS: intPtr(90970), LastLapTimeMS: intPtr(90850), BestLapTimeMS: intPtr(90780), FuelLiters: floatPtr(4.0), FuelLapsRemainingEstimate: floatPtr(1.9), ProjectedFuelToFinishLiters: floatPtr(-0.1)},
	}
}
