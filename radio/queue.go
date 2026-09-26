package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

type Queue struct {
	root     string
	stations map[string]bool
	mu       sync.Mutex
}

func newQueue(root string, stations []Station) (*Queue, error) {
	absolute, err := filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	q := &Queue{root: absolute, stations: map[string]bool{}}
	for _, station := range stations {
		q.stations[station.ID] = true
		for _, folder := range []string{"ready", "playing", "fallback"} {
			if err := os.MkdirAll(filepath.Join(q.root, station.ID, folder), 0775); err != nil {
				return nil, err
			}
		}
	}
	return q, nil
}

func audioFiles(folder string) ([]string, error) {
	entries, err := os.ReadDir(folder)
	if err != nil {
		return nil, err
	}
	var files []string
	for _, entry := range entries {
		if entry.Type().IsRegular() && filepath.Ext(entry.Name()) == ".flac" {
			files = append(files, filepath.Join(folder, entry.Name()))
		}
	}
	return files, nil
}

func (q *Queue) recover() error {
	q.mu.Lock()
	defer q.mu.Unlock()
	for id := range q.stations {
		files, err := audioFiles(filepath.Join(q.root, id, "playing"))
		if err != nil {
			return err
		}
		for _, file := range files {
			target := filepath.Join(q.root, id, "ready", filepath.Base(file))
			if _, err := os.Lstat(target); !errors.Is(err, os.ErrNotExist) {
				return fmt.Errorf("queue recovery collision: %s", target)
			}
			if err := os.Rename(file, target); err != nil {
				return err
			}
		}
	}
	return nil
}

func (q *Queue) next(id string) (string, error) {
	q.mu.Lock()
	defer q.mu.Unlock()
	if !q.stations[id] {
		return "", errors.New("unknown station")
	}
	files, err := audioFiles(filepath.Join(q.root, id, "ready"))
	if err != nil {
		return "", err
	}
	for _, file := range files {
		target := filepath.Join(q.root, id, "playing", filepath.Base(file))
		if err := os.Rename(file, target); errors.Is(err, os.ErrNotExist) {
			continue
		} else if err != nil {
			return "", err
		}
		return target, nil
	}
	return "", nil
}
