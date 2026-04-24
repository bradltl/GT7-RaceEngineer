package gt7

import (
	"encoding/binary"
	"math"
	"testing"
)

func TestDecoderDecodeSyntheticPacket(t *testing.T) {
	plaintext := make([]byte, minPacketLen)
	binary.LittleEndian.PutUint32(plaintext[0:4], packetMagic)
	binary.LittleEndian.PutUint32(plaintext[0x40:0x44], 0x12345678)
	writeFloat32(plaintext, 0x3C, 8123.5)
	writeFloat32(plaintext, 0x44, 7.25)
	writeFloat32(plaintext, 0x48, 40.0)
	writeFloat32(plaintext, 0x4C, 61.111111)
	writeFloat32(plaintext, 0x60, 86.0)
	writeFloat32(plaintext, 0x64, 87.0)
	writeFloat32(plaintext, 0x68, 88.0)
	writeFloat32(plaintext, 0x6C, 89.0)
	binary.LittleEndian.PutUint32(plaintext[0x70:0x74], 42)
	binary.LittleEndian.PutUint16(plaintext[0x74:0x76], 7)
	binary.LittleEndian.PutUint16(plaintext[0x76:0x78], 15)
	binary.LittleEndian.PutUint32(plaintext[0x78:0x7C], 90321)
	binary.LittleEndian.PutUint32(plaintext[0x7C:0x80], 91456)
	binary.LittleEndian.PutUint16(plaintext[0x8E:0x90], 1<<0|1<<11)
	plaintext[0x90] = 0x03
	plaintext[0x91] = 191
	plaintext[0x92] = 64

	writeFloat32(plaintext, 0xA4, 50.0)
	writeFloat32(plaintext, 0xA8, 51.0)
	writeFloat32(plaintext, 0xAC, 52.0)
	writeFloat32(plaintext, 0xB0, 53.0)
	writeFloat32(plaintext, 0xB4, 0.31)
	writeFloat32(plaintext, 0xB8, 0.32)
	writeFloat32(plaintext, 0xBC, 0.33)
	writeFloat32(plaintext, 0xC0, 0.34)

	var key [32]byte
	copy(key[:], []byte(packetKey))
	nonce := nonceForType("A", 0x12345678)
	ciphertext := make([]byte, len(plaintext))
	xorKeyStream(ciphertext, plaintext, nonce[:], &key)
	binary.LittleEndian.PutUint32(ciphertext[0x40:0x44], 0x12345678)

	decoder := NewDecoder("A")
	decoded, err := decoder.Decode(ciphertext)
	if err != nil {
		t.Fatalf("decode failed: %v", err)
	}

	if decoded.Snapshot.EventID != "gt7-42" {
		t.Fatalf("event id mismatch: got %q", decoded.Snapshot.EventID)
	}
	if decoded.Snapshot.SourceMode != "live" {
		t.Fatalf("source mode mismatch: got %q", decoded.Snapshot.SourceMode)
	}
	if got := decoded.Snapshot.LapNumber; got != 7 {
		t.Fatalf("lap number mismatch: got %d", got)
	}
	if decoded.Snapshot.LapsRemaining == nil || *decoded.Snapshot.LapsRemaining != 15 {
		t.Fatalf("laps remaining mismatch: %#v", decoded.Snapshot.LapsRemaining)
	}
	if decoded.Snapshot.FuelLiters == nil || math.Abs(*decoded.Snapshot.FuelLiters-7.25) > 1e-6 {
		t.Fatalf("fuel liters mismatch: %#v", decoded.Snapshot.FuelLiters)
	}
	if decoded.Snapshot.FuelCapacityLiters == nil || math.Abs(*decoded.Snapshot.FuelCapacityLiters-40.0) > 1e-6 {
		t.Fatalf("fuel capacity mismatch: %#v", decoded.Snapshot.FuelCapacityLiters)
	}
	if decoded.Snapshot.SpeedKPH == nil || math.Abs(*decoded.Snapshot.SpeedKPH-220.0) > 1e-3 {
		t.Fatalf("speed mismatch: %#v", decoded.Snapshot.SpeedKPH)
	}
	if decoded.Snapshot.ThrottlePct == nil || math.Abs(*decoded.Snapshot.ThrottlePct-74.9019607843) > 1e-6 {
		t.Fatalf("throttle mismatch: %#v", decoded.Snapshot.ThrottlePct)
	}
	if decoded.Snapshot.BrakePct == nil || math.Abs(*decoded.Snapshot.BrakePct-25.0980392157) > 1e-6 {
		t.Fatalf("brake mismatch: %#v", decoded.Snapshot.BrakePct)
	}
	if decoded.Snapshot.Gear == nil || *decoded.Snapshot.Gear != 3 {
		t.Fatalf("gear mismatch: %#v", decoded.Snapshot.Gear)
	}
	if decoded.Snapshot.Flags["car_on_track"] != true || decoded.Snapshot.Flags["tcs_active"] != true {
		t.Fatalf("flags mismatch: %#v", decoded.Snapshot.Flags)
	}
}

func TestPacketMask(t *testing.T) {
	tests := []struct {
		heartbeat string
		want      uint32
	}{
		{"A", 0xDEADBEAF},
		{"B", 0xDEADBEEF},
		{"~", 0x55FABB4F},
	}
	for _, tc := range tests {
		got, err := packetMask(tc.heartbeat)
		if err != nil {
			t.Fatalf("packetMask(%q) returned error: %v", tc.heartbeat, err)
		}
		if got != tc.want {
			t.Fatalf("packetMask(%q) = 0x%08x want 0x%08x", tc.heartbeat, got, tc.want)
		}
	}
}

func nonceForType(heartbeatType string, ivSeed uint32) [8]byte {
	mask, _ := packetMask(heartbeatType)
	var nonce [8]byte
	binary.LittleEndian.PutUint32(nonce[0:4], ivSeed^mask)
	binary.LittleEndian.PutUint32(nonce[4:8], ivSeed)
	return nonce
}

func writeFloat32(buf []byte, offset int, value float32) {
	binary.LittleEndian.PutUint32(buf[offset:offset+4], math.Float32bits(value))
}
