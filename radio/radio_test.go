package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func testQueue(t *testing.T) *Queue {
	t.Helper()
	q, err := newQueue(t.TempDir(), []Station{{ID: "one"}, {ID: "two"}})
	if err != nil {
		t.Fatal(err)
	}
	return q
}

func put(t *testing.T, path string) {
	t.Helper()
	if err := os.WriteFile(path, []byte("audio"), 0600); err != nil {
		t.Fatal(err)
	}
}

func TestQueueClaimAndRecover(t *testing.T) {
	q := testQueue(t)
	put(t, filepath.Join(q.root, "one", "ready", "002.flac"))
	put(t, filepath.Join(q.root, "one", "ready", "001.flac"))
	put(t, filepath.Join(q.root, "one", "ready", "unfinished.tmp"))
	put(t, filepath.Join(q.root, "two", "ready", "001.flac"))
	path, err := q.next("one")
	if err != nil || filepath.Base(path) != "001.flac" {
		t.Fatalf("unexpected claim: %s %v", path, err)
	}
	if _, err := os.Stat(filepath.Join(q.root, "one", "ready", "001.flac")); !os.IsNotExist(err) {
		t.Fatal("claim remained ready")
	}
	if _, err := q.next("../two"); err == nil {
		t.Fatal("accepted invalid station")
	}
	if err := q.recover(); err != nil {
		t.Fatal(err)
	}
	if files, _ := audioFiles(filepath.Join(q.root, "one", "playing")); len(files) != 0 {
		t.Fatal("recovery left claims")
	}
	if files, _ := audioFiles(filepath.Join(q.root, "two", "ready")); len(files) != 1 {
		t.Fatal("modified another station")
	}
}

func TestConcurrentClaimsAndSymlinks(t *testing.T) {
	q := testQueue(t)
	put(t, filepath.Join(q.root, "one", "ready", "001.flac"))
	if err := os.Symlink("/etc/passwd", filepath.Join(q.root, "one", "ready", "000.flac")); err != nil {
		t.Fatal(err)
	}
	claims := make(chan string, 10)
	var wg sync.WaitGroup
	for range 10 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			p, err := q.next("one")
			if err != nil {
				t.Error(err)
			}
			if p != "" {
				claims <- p
			}
		}()
	}
	wg.Wait()
	close(claims)
	if len(claims) != 1 {
		t.Fatalf("expected one claim, got %d", len(claims))
	}
}

func TestProxyIsolationAndStreaming(t *testing.T) {
	release := make(chan struct{})
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/streams/one.mp3" || r.Header.Get("Authorization") != "" {
			t.Error("unexpected upstream request")
		}
		w.Header().Set("Content-Type", "audio/mpeg")
		_, _ = io.WriteString(w, "audio")
		w.(http.Flusher).Flush()
		<-release
	}))
	defer upstream.Close()
	u, _ := url.Parse(upstream.URL)
	c := Config{Stations: []Station{{ID: "one"}}}
	server := httptest.NewServer(publicHandler(c, u))
	defer server.Close()
	client := &http.Client{Timeout: 2 * time.Second}
	for _, path := range []string{"/admin/stats", "/status-json.xsl", "/next/one", "/streams/missing.mp3", "/streams/one.mp3?admin=true"} {
		response, err := client.Get(server.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		response.Body.Close()
		if response.StatusCode != 404 {
			t.Errorf("exposed %s", path)
		}
	}
	request, _ := http.NewRequest("GET", server.URL+"/streams/one.mp3", nil)
	request.Header.Set("Authorization", "secret")
	response, err := client.Do(request)
	if err != nil {
		close(release)
		t.Fatal(err)
	}
	defer response.Body.Close()
	data := make([]byte, 5)
	_, err = io.ReadFull(response.Body, data)
	close(release)
	if err != nil || string(data) != "audio" {
		t.Fatalf("stream buffered: %q %v", data, err)
	}
}

func TestHealthRequiresEveryMount(t *testing.T) {
	body := `{"icestats":{"source":{"listenurl":"http://localhost/streams/one.mp3"}}}`
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, body) }))
	defer upstream.Close()
	u, _ := url.Parse(upstream.URL)
	for _, tc := range []struct {
		stations []Station
		status   int
	}{
		{[]Station{{ID: "one"}}, 200}, {[]Station{{ID: "one"}, {ID: "two"}}, 503},
	} {
		response := httptest.NewRecorder()
		publicHandler(Config{Stations: tc.stations}, u).ServeHTTP(response, httptest.NewRequest("GET", "/healthz", nil))
		if response.Code != tc.status {
			t.Fatalf("unexpected status: %d", response.Code)
		}
	}
	body = `{"icestats":{"source":[{"listenurl":"http://localhost/streams/one.mp3"},{"listenurl":"http://localhost/streams/two.mp3"}]}}`
	response := httptest.NewRecorder()
	publicHandler(Config{Stations: []Station{{ID: "one"}, {ID: "two"}}}, u).ServeHTTP(response, httptest.NewRequest("GET", "/healthz", nil))
	if response.Code != 200 {
		t.Fatal("multiple sources not healthy")
	}
}

func TestConfig(t *testing.T) {
	data, err := os.ReadFile("../stations.yml")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "stations.yml")
	for _, tc := range []struct {
		text  string
		valid bool
	}{
		{string(data), true},
		{strings.ReplaceAll(string(data), "night-drive", "../escape"), false},
		{string(data) + "unknown: true\n", false},
		{strings.ReplaceAll(string(data), "crossfade_seconds: 5", "crossfade_seconds: 100"), false},
		{string(data) + "---\nother: true\n", false},
	} {
		if err := os.WriteFile(path, []byte(tc.text), 0600); err != nil {
			t.Fatal(err)
		}
		_, err := loadConfig(path)
		if (err == nil) != tc.valid {
			t.Fatalf("unexpected validation: %v", err)
		}
	}
}

func TestLiquidsoapStringDoesNotInterpolate(t *testing.T) {
	encoded := liquidsoapString(`name #{system("unexpected")} # quote "`)
	if strings.Contains(encoded, "#{") {
		t.Fatalf("unsafe interpolation: %s", encoded)
	}
}
