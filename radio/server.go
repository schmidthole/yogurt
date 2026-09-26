package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"
)

func publicHandler(c Config, upstream *url.URL) http.Handler {
	streams := map[string]bool{}
	for _, station := range c.Stations {
		streams["/streams/"+station.ID+".mp3"] = true
	}
	proxy := httputil.NewSingleHostReverseProxy(upstream)
	proxy.FlushInterval = -1
	proxy.Transport = &http.Transport{ResponseHeaderTimeout: 10 * time.Second}
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		log.Printf("stream unavailable: %s", strings.ToLower(err.Error()))
		http.Error(w, "stream unavailable", http.StatusBadGateway)
	}
	client := &http.Client{Timeout: 3 * time.Second}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			http.Error(w, "method not allowed", 405)
			return
		}
		if r.URL.Path == "/healthz" {
			response, err := client.Get(upstream.String() + "/status-json.xsl")
			if err != nil {
				http.Error(w, "radio unavailable", 503)
				return
			}
			defer response.Body.Close()
			var status struct {
				Stats struct {
					Source json.RawMessage `json:"source"`
				} `json:"icestats"`
			}
			if response.StatusCode != 200 || json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(&status) != nil {
				http.Error(w, "radio unavailable", 503)
				return
			}
			var sources []struct {
				ListenURL string `json:"listenurl"`
			}
			if len(status.Stats.Source) > 0 && status.Stats.Source[0] == '[' {
				_ = json.Unmarshal(status.Stats.Source, &sources)
			} else {
				var source struct {
					ListenURL string `json:"listenurl"`
				}
				if json.Unmarshal(status.Stats.Source, &source) == nil {
					sources = append(sources, source)
				}
			}
			active := map[string]bool{}
			for _, source := range sources {
				if u, err := url.Parse(source.ListenURL); err == nil {
					active[u.Path] = true
				}
			}
			for path := range streams {
				if !active[path] {
					http.Error(w, "station unavailable", 503)
					return
				}
			}
			fmt.Fprintln(w, "ok")
			return
		}
		if !streams[r.URL.Path] || r.URL.RawQuery != "" {
			http.NotFound(w, r)
			return
		}
		r.Header.Del("Authorization")
		r.Header.Del("Cookie")
		proxy.ServeHTTP(w, r)
	})
}

func internalHandler(q *Queue) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /next/{station}", func(w http.ResponseWriter, r *http.Request) {
		path, err := q.next(r.PathValue("station"))
		if err != nil {
			http.Error(w, "queue unavailable", 503)
			log.Printf("queue error: %s", strings.ToLower(err.Error()))
			return
		}
		w.Header().Set("Content-Type", "text/plain")
		fmt.Fprint(w, path)
	})
	// called by a fresh liquidsoap process before it requests any files
	mux.HandleFunc("POST /recover", func(w http.ResponseWriter, r *http.Request) {
		if err := q.recover(); err != nil {
			http.Error(w, "recovery failed", 500)
			return
		}
		fmt.Fprint(w, "ok")
	})
	return mux
}
