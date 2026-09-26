package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"
	"unicode/utf8"

	"gopkg.in/yaml.v3"
)

type Song struct {
	Lyrics        string `yaml:"lyrics,omitempty"`
	VocalLanguage string `yaml:"vocal_language,omitempty"`
	Prompt        string `yaml:"prompt"`
	Seconds       int    `yaml:"seconds"`
	BPM           int    `yaml:"bpm"`
	Key           string `yaml:"key"`
}

type Station struct {
	ID     string `yaml:"id"`
	Name   string `yaml:"name"`
	Prompt string `yaml:"prompt"`
	Songs  []Song `yaml:"songs,omitempty"`
}

type Config struct {
	Segment   int       `yaml:"segment_seconds"`
	Crossfade int       `yaml:"crossfade_seconds"`
	Low       int       `yaml:"buffer_low_seconds"`
	Target    int       `yaml:"buffer_target_seconds"`
	Stations  []Station `yaml:"stations"`
}

var vocalLanguage = regexp.MustCompile(`^([a-z]{2}|unknown)$`)

var slug = regexp.MustCompile(`^[a-z0-9]+(-[a-z0-9]+)*$`)

func loadConfig(path string) (Config, error) {
	var c Config
	f, err := os.Open(path)
	if err != nil {
		return c, err
	}
	defer f.Close()
	decoder := yaml.NewDecoder(f)
	decoder.KnownFields(true)
	if err := decoder.Decode(&c); err != nil {
		return c, err
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		return c, errors.New("expected one configuration document")
	}
	if c.Segment < 10 || c.Segment > 600 || c.Crossfade < 0 || c.Crossfade*2 >= c.Segment || c.Low <= 0 || c.Target < c.Low || c.Target > 86400 || len(c.Stations) == 0 {
		return c, errors.New("invalid station configuration")
	}
	seen := map[string]bool{}
	for _, s := range c.Stations {
		if !slug.MatchString(s.ID) || seen[s.ID] || strings.TrimSpace(s.Name) == "" || strings.TrimSpace(s.Prompt) == "" || strings.IndexFunc(s.Name, func(r rune) bool { return r < 32 }) >= 0 {
			return c, fmt.Errorf("invalid station: %s", s.ID)
		}
		for _, song := range s.Songs {
			if utf8.RuneCountInString(song.Lyrics) > 4096 || (song.VocalLanguage != "" && !vocalLanguage.MatchString(song.VocalLanguage)) || (song.VocalLanguage != "" && song.VocalLanguage != "unknown" && strings.TrimSpace(song.Lyrics) == "") {
				return c, fmt.Errorf("invalid vocal profile for station: %s", s.ID)
			}
			if strings.TrimSpace(song.Prompt) == "" || strings.TrimSpace(song.Key) == "" || song.Seconds < 10 || song.Seconds > 480 || song.BPM < 30 || song.BPM > 300 || c.Crossfade*2 >= song.Seconds {
				return c, fmt.Errorf("invalid song profile for station: %s", s.ID)
			}
		}
		seen[s.ID] = true
	}
	return c, nil
}
