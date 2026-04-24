package gt7

import (
	"encoding/binary"
	"errors"
	"fmt"
	"math"
	"strings"

	"gt7race/telemetry-capture/internal/model"
)

const (
	packetMagic  = 0x47375330
	packetKey    = "Simulator Interface Packet GT7 ver 0.0"
	minPacketLen = 0x128
)

// Decoder turns encrypted GT7 packets into normalized telemetry snapshots.
// TODO(gt7-field-validation): the packet layout below is based on public community
// references. Any field that is not validated live should remain optional in the
// normalized contract until we verify it against a real PS5 capture.
type Decoder struct {
	HeartbeatType string
}

type DecodedPacket struct {
	Decrypted []byte
	Snapshot  model.TelemetrySnapshot
}

func NewDecoder(heartbeatType string) *Decoder {
	heartbeatType = strings.TrimSpace(heartbeatType)
	if heartbeatType == "" {
		heartbeatType = "A"
	}
	return &Decoder{HeartbeatType: heartbeatType}
}

func (d *Decoder) Decode(encrypted []byte) (*DecodedPacket, error) {
	decrypted, err := d.decrypt(encrypted)
	if err != nil {
		return nil, err
	}
	snapshot, err := d.parseSnapshot(decrypted)
	if err != nil {
		return nil, err
	}
	return &DecodedPacket{
		Decrypted: decrypted,
		Snapshot:  snapshot,
	}, nil
}

func (d *Decoder) decrypt(encrypted []byte) ([]byte, error) {
	if len(encrypted) < minPacketLen {
		return nil, fmt.Errorf("packet too short: got %d want >= %d", len(encrypted), minPacketLen)
	}

	ivSeed := binary.LittleEndian.Uint32(encrypted[0x40:0x44])
	mask, err := packetMask(d.HeartbeatType)
	if err != nil {
		return nil, err
	}

	iv := make([]byte, 8)
	binary.LittleEndian.PutUint32(iv[0:4], ivSeed^mask)
	binary.LittleEndian.PutUint32(iv[4:8], ivSeed)

	var key [32]byte
	copy(key[:], []byte(packetKey))
	decrypted := make([]byte, len(encrypted))
	xorKeyStream(decrypted, encrypted, iv, &key)

	magic := int32(binary.LittleEndian.Uint32(decrypted[0:4]))
	if magic != packetMagic {
		return nil, fmt.Errorf("invalid packet magic: 0x%08x", uint32(magic))
	}
	return decrypted, nil
}

func packetMask(heartbeatType string) (uint32, error) {
	switch strings.ToUpper(strings.TrimSpace(heartbeatType)) {
	case "A", "":
		return 0xDEADBEAF, nil
	case "B":
		return 0xDEADBEEF, nil
	case "~":
		return 0x55FABB4F, nil
	default:
		return 0, fmt.Errorf("unsupported heartbeat type %q", heartbeatType)
	}
}

func (d *Decoder) parseSnapshot(packet []byte) (model.TelemetrySnapshot, error) {
	if len(packet) < minPacketLen {
		return model.TelemetrySnapshot{}, errors.New("decrypted packet truncated")
	}

	packetID := int(int32At(packet, 0x70))
	lapNumber := int(int16At(packet, 0x74))
	totalLaps := int(int16At(packet, 0x76))
	bestLap := int(int32At(packet, 0x78))
	lastLap := int(int32At(packet, 0x7C))
	speedKPH := float64At(packet, 0x4C) * 3.6
	throttle := float64(packet[0x91]) / 255.0 * 100.0
	brake := float64(packet[0x92]) / 255.0 * 100.0
	gearByte := packet[0x90]
	flags := int16At(packet, 0x8E)

	snapshot := model.TelemetrySnapshot{
		EventID:            fmt.Sprintf("gt7-%d", packetID),
		TimestampMS:        0,
		SessionID:          "",
		Source:             "gt7-udp",
		SourceMode:         "live",
		ConnectionState:    "connected",
		LapNumber:          lapNumber,
		LapsRemaining:      &totalLaps,
		LastLapTimeMS:      intPtrIfPositive(lastLap),
		BestLapTimeMS:      intPtrIfPositive(bestLap),
		FuelLiters:         float64Ptr(float64At(packet, 0x44)),
		FuelCapacityLiters: float64Ptr(float64At(packet, 0x48)),
		SpeedKPH:           float64Ptr(speedKPH),
		ThrottlePct:        float64Ptr(throttle),
		BrakePct:           float64Ptr(brake),
		Gear:               intPtr(currentGearFromByte(gearByte)),
		RPM:                intPtr(int(math.Round(float64At(packet, 0x3C)))),
		Flags:              decodeFlags(flags),
		Raw:                map[string]any{},
		ValidationWarnings: []string{},
	}

	snapshot.Raw["packet_id"] = packetID
	snapshot.Raw["current_lap"] = lapNumber
	snapshot.Raw["total_laps"] = totalLaps
	snapshot.Raw["best_lap_time_ms"] = bestLap
	snapshot.Raw["last_lap_time_ms"] = lastLap
	snapshot.Raw["speed_mps"] = float64At(packet, 0x4C)
	snapshot.Raw["throttle_raw"] = packet[0x91]
	snapshot.Raw["brake_raw"] = packet[0x92]
	snapshot.Raw["gear_raw"] = gearByte
	snapshot.Raw["flags_raw"] = flags

	tireTemps := [4]float64{
		float64At(packet, 0x60),
		float64At(packet, 0x64),
		float64At(packet, 0x68),
		float64At(packet, 0x6C),
	}
	snapshot.Raw["tire_temps_c"] = tireTemps
	snapshot.Raw["wheel_rps"] = [4]float64{
		float64At(packet, 0xA4),
		float64At(packet, 0xA8),
		float64At(packet, 0xAC),
		float64At(packet, 0xB0),
	}
	snapshot.Raw["tyre_radius_m"] = [4]float64{
		float64At(packet, 0xB4),
		float64At(packet, 0xB8),
		float64At(packet, 0xBC),
		float64At(packet, 0xC0),
	}

	if snapshot.FuelLiters == nil || snapshot.FuelCapacityLiters == nil {
		snapshot.ValidationWarnings = append(snapshot.ValidationWarnings, "fuel fields are optional until validated live")
	}
	if snapshot.SpeedKPH == nil {
		snapshot.ValidationWarnings = append(snapshot.ValidationWarnings, "speed field missing from live decode")
	}
	return snapshot, nil
}

func decodeFlags(flags int16) map[string]bool {
	return map[string]bool{
		"car_on_track":           flags&(1<<0) != 0,
		"paused":                 flags&(1<<1) != 0,
		"loading_or_processing":  flags&(1<<2) != 0,
		"in_gear":                flags&(1<<3) != 0,
		"has_turbo":              flags&(1<<4) != 0,
		"rev_limit_alert_active": flags&(1<<5) != 0,
		"handbrake_active":       flags&(1<<6) != 0,
		"lights_active":          flags&(1<<7) != 0,
		"high_beams_active":      flags&(1<<8) != 0,
		"low_beams_active":       flags&(1<<9) != 0,
		"asm_active":             flags&(1<<10) != 0,
		"tcs_active":             flags&(1<<11) != 0,
	}
}

func int32At(b []byte, offset int) int32 {
	return int32(binary.LittleEndian.Uint32(b[offset : offset+4]))
}

func int16At(b []byte, offset int) int16 {
	return int16(binary.LittleEndian.Uint16(b[offset : offset+2]))
}

func float64At(b []byte, offset int) float64 {
	return float64(math.Float32frombits(binary.LittleEndian.Uint32(b[offset : offset+4])))
}

func currentGearFromByte(v byte) int {
	gear := int(v & 0x0F)
	if gear > 15 {
		return 0
	}
	return gear
}

func intPtr(v int) *int {
	return &v
}

func intPtrIfPositive(v int) *int {
	if v < 0 {
		return nil
	}
	return &v
}

func float64Ptr(v float64) *float64 {
	return &v
}
