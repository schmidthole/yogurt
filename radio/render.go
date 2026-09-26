package main

import (
	"bytes"
	"encoding/xml"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

func liquidsoapString(s string) string {
	parts := strings.Split(s, "#")
	for i := range parts {
		parts[i] = strconv.Quote(parts[i])
	}
	return "(" + strings.Join(parts, ` ^ "#" ^ `) + ")"
}

func xmlText(s string) string {
	var b bytes.Buffer
	_ = xml.EscapeText(&b, []byte(s))
	return b.String()
}

func render(c Config, q *Queue, dir, password, admin string) error {
	if password == "" || admin == "" {
		return fmt.Errorf("icecast_source_password and icecast_admin_password are required")
	}
	if err := os.MkdirAll(dir, 0755); err != nil {
		return err
	}
	var script strings.Builder
	script.WriteString("settings.log.stdout.set(true)\nsettings.log.file.set(false)\nsettings.server.telnet.set(false)\n")
	for index, station := range c.Stations {
		fallback, err := audioFiles(filepath.Join(q.root, station.ID, "fallback"))
		if err != nil || len(fallback) == 0 {
			return fmt.Errorf("missing fallback for %s; start the generator first", station.ID)
		}
		// decode each fallback now so an invalid file cannot become the safety source
		for _, path := range fallback {
			if output, err := exec.Command("ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", path, "-f", "null", "-").CombinedOutput(); err != nil {
				return fmt.Errorf("invalid fallback for %s: %s", station.ID, strings.ToLower(string(output)))
			}
		}
		fmt.Fprintf(&script, `
def next_%d() =
  response = http.post(timeout_ms=3000, "http://127.0.0.1:8081/next/%s")
  path = if response.status_code == 200 then "#{response}" else "" end
  if path == "" then request.create("") else request.create(temporary=true, path) end
end
fresh_%d = request.dynamic(prefetch=1, retry_delay=1., next_%d)
backup_%d = fallback([playlist(%s), single(%s)])
station_%d = fallback(track_sensitive=true, [fresh_%d, backup_%d])
station_%d = mksafe(crossfade(duration=%d., fade_in=%d., fade_out=%d., station_%d))
output.icecast(%%mp3(bitrate=192, samplerate=48000, stereo=true), host="127.0.0.1", port=8000, password=%s, mount=%s, name=%s, public=false, station_%d)
`, index, station.ID, index, index, index, liquidsoapString(filepath.Join(q.root, station.ID, "fallback")), liquidsoapString(fallback[0]), index, index, index, index, c.Crossfade, c.Crossfade, c.Crossfade, index, liquidsoapString(password), liquidsoapString("/streams/"+station.ID+".mp3"), liquidsoapString(station.Name), index)
	}
	if err := os.WriteFile(filepath.Join(dir, "radio.liq"), []byte(script.String()), 0600); err != nil {
		return err
	}
	icecast := fmt.Sprintf(`<icecast>
  <location>yogurt</location><admin>admin@localhost</admin>
  <limits><clients>100</clients><sources>%d</sources><queue-size>524288</queue-size><source-timeout>10</source-timeout></limits>
  <authentication><source-password>%s</source-password><admin-user>admin</admin-user><admin-password>%s</admin-password></authentication>
  <hostname>localhost</hostname>
  <listen-socket><port>8000</port><bind-address>127.0.0.1</bind-address></listen-socket>
  <fileserve>1</fileserve>
  <paths><basedir>/usr/share/icecast2</basedir><logdir>/tmp</logdir><webroot>/usr/share/icecast2/web</webroot><adminroot>/usr/share/icecast2/admin</adminroot></paths>
  <logging><accesslog>-</accesslog><errorlog>-</errorlog><loglevel>2</loglevel></logging>
</icecast>
`, len(c.Stations), xmlText(password), xmlText(admin))
	return os.WriteFile(filepath.Join(dir, "icecast.xml"), []byte(icecast), 0600)
}
