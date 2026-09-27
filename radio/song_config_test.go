package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSongProfiles(t *testing.T) {
	original, err := os.ReadFile("../stations.yml")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "stations.yml")
	for _, tc := range []struct {
		name, text string
		valid      bool
	}{
		{"approved profiles", string(original), true},
		{"explicit metadata", strings.Replace(string(original), "    seconds: 180", "    seconds: 180\n    bpm: 95\n    key: E minor", 1), true},
		{"null tempo", strings.Replace(string(original), "    seconds: 180", "    seconds: 180\n    bpm: null", 1), true},
		{"too fast", strings.Replace(string(original), "    seconds: 180", "    seconds: 180\n    bpm: 301", 1), false},
		{"invalid language", strings.Replace(string(original), "vocal_language: ru", "vocal_language: russian", 1), false},
		{"too long", strings.Replace(string(original), "    seconds: 180", "    seconds: 481", 1), false},
		{"invalid tempo", strings.Replace(string(original), "    seconds: 180", "    seconds: 180\n    bpm: 0", 1), false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if err := os.WriteFile(path, []byte(tc.text), 0600); err != nil {
				t.Fatal(err)
			}
			cfg, err := loadConfig(path)
			if (err == nil) != tc.valid {
				t.Fatalf("valid=%v err=%v", tc.valid, err)
			}
			if tc.valid && len(cfg.Stations[0].Songs) != 5 {
				t.Fatal("lost song profiles")
			}
		})
	}
}
