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
		{"too long", strings.Replace(string(original), "    seconds: 180", "    seconds: 481", 1), false},
		{"invalid tempo", strings.Replace(string(original), "bpm: 82", "bpm: 0", 1), false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if err := os.WriteFile(path, []byte(tc.text), 0600); err != nil {
				t.Fatal(err)
			}
			cfg, err := loadConfig(path)
			if (err == nil) != tc.valid {
				t.Fatalf("valid=%v err=%v", tc.valid, err)
			}
			if tc.valid && len(cfg.Stations[0].Songs) != 3 {
				t.Fatal("lost song profiles")
			}
		})
	}
}
