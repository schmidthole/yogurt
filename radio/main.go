package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

func main() {
	configPath := flag.String("config", "/app/stations.yml", "station configuration")
	root := flag.String("root", "/radio", "shared queue directory")
	prepare := flag.Bool("prepare", false, "render runtime configuration")
	dir := flag.String("runtime", "/run/yogurt", "runtime configuration directory")
	flag.Parse()
	log.SetFlags(0)
	if err := run(*configPath, *root, *prepare, *dir); err != nil {
		log.Fatal(strings.ToLower(err.Error()))
	}
}

func run(configPath, root string, prepare bool, dir string) error {
	c, err := loadConfig(configPath)
	if err != nil {
		return err
	}
	q, err := newQueue(root, c.Stations)
	if err != nil {
		return err
	}
	if prepare {
		return render(c, q, dir, os.Getenv("ICECAST_SOURCE_PASSWORD"), os.Getenv("ICECAST_ADMIN_PASSWORD"))
	}
	upstream, _ := url.Parse("http://127.0.0.1:8000")
	public := &http.Server{Addr: ":80", Handler: publicHandler(c, upstream), ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 60 * time.Second}
	internal := &http.Server{Addr: "127.0.0.1:8081", Handler: internalHandler(q), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 5 * time.Second, WriteTimeout: 5 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	failures := make(chan error, 2)
	for _, server := range []*http.Server{public, internal} {
		go func(s *http.Server) { failures <- s.ListenAndServe() }(server)
	}
	var failure error
	select {
	case <-ctx.Done():
	case failure = <-failures:
	}
	// live listeners must reconnect after a server restart
	_ = public.Close()
	_ = internal.Close()
	return failure
}
