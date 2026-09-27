# yogurt

self-hosted ai radio: one gpu generator and one radio container, deployed with lord. the initial configuration broadcasts one station; additional stations share the same model and have independent queues and icecast mountpoints.

```text
ACE-Step full songs -> normalized flac queues -> liquidsoap -> icecast
                                                               |
                                                  go stream proxy :80
                                                               |
                                                          traefik
                                                               |
                                                    radio macos app
```

there is no station web player, catalog api, or database. add this url in [radio](https://github.com/pom11/Radio) settings after deployment:

```text
http://localhost:8080/streams/night-drive.mp3
```

## local deployment on this host

The checked-in Lord configs target this Fedora machine over localhost SSH using
`/home/taylor/.ssh/lord-local`. The radio publishes on `127.0.0.1:8080` and the home Wi-Fi address
`192.168.86.31:8080`; it does not provision Traefik or public certificates. This requires a Lord build with
`ports` support (local Lord commit `06b341f`).

- Health: `http://localhost:8080/healthz`
- Stream on this machine: `http://localhost:8080/streams/night-drive.mp3`
- Stream on the home network: `http://192.168.86.31:8080/streams/night-drive.mp3`

Reserve `192.168.86.31` for this machine in the home router's DHCP settings to
keep the LAN URL and explicit Docker binding stable. The active FedoraWorkstation
firewall zone already permits TCP 8080. No router port forwarding is configured
by this deployment. Icecast administration and queue endpoints remain internal.

The NVIDIA Container Toolkit supplies GPU access. Model data is stored under
`/var/yogurt-generator`; audio queues and fallback audio live in `/srv/yogurt`.
The ignored `radio.env` contains the local Icecast credentials. Keep these files
and directories across deployments. SSH listens only on loopback; the deployment
key is restricted to localhost connections. Docker and SSH start on boot, and
Lord configures the containers to restart unless stopped.

From this directory, redeploy with:

```sh
lord -config generator -deploy
# Wait for generation to produce fallback/seed.flac and ready audio.
lord -config radio -deploy
```

The station is also available privately over Tailscale:

`https://ra.minskin-godzilla.ts.net/streams/night-drive.mp3`

Connect the listening device (including iOS) to the same tailnet, then open that
URL in a player that supports network audio streams. Tailnet access rules apply.
The host runs Tailscale at startup, with persistent background Serve forwarding
HTTPS to `http://127.0.0.1:8080`. LAN access remains available at the address above.
Funnel is not enabled; no public router port forwarding is needed.

To reproduce on another host, install and authenticate Tailscale, then run
`sudo tailscale serve --bg http://127.0.0.1:8080`. Use the HTTPS URL reported by
Serve with `/streams/night-drive.mp3` appended. Inspect with
`tailscale serve status`; disable with `sudo tailscale serve --https=443 off`.

## development

requirements: go 1.23+, uv, and docker for audio/container tests. no gpu or model assets are needed for these checks.

```sh
make setup
make fmt
make test
make test-audio
make integration
```

`make test` covers configuration, scheduling, atomic publication, failure cleanup, model reuse/context isolation, queue claims/recovery, http routing, readiness, and unbuffered proxying. its real-audio test is skipped if ffmpeg/ffprobe are absent locally; `make test-audio` runs it in a cpu container with ffmpeg installed.

`make integration` builds the radio image and creates two temporary fixture stations. it checks playable streams, protected internal routes, consumption/cleanup, fallback, new audio arriving, child-process restarts, and container restart. it removes its temporary container and data afterward. test ports bind only to localhost. the deployed station list still contains only one station.

```sh
make radio
make ace-runtime  # once per pinned ACE-Step revision
make generator
```

`make ace-runtime` builds the official ACE-Step Dockerfile at revision `ca1e85fe9430179831e6bc6be790c332190a3866`. Its upstream `uv.lock` pins the Python 3.11 / PyTorch / CUDA 12.8 runtime. `make generator` builds the Yogurt adapter on that local runtime image for linux/amd64. it is a large image and needs no gpu at build time. the model itself is downloaded separately on the host; it is not baked into the image. the radio build supports amd64 and arm64.

## station configuration

edit `stations.yml`. ids must be unique lowercase slugs. each station has a name and prompt. complete songs default to 180 seconds with five-second crossfades. optional `songs` profiles require `prompt` and `seconds` (10–480). `bpm` (30–300) and `key` are optional overrides; omit them to let ACE-Step choose musical metadata for each render. the generator randomly selects a profile and a fresh seed per song. supplied profiles use broad mood/style descriptions: three dramatic cinematic synthwave lo-fi themes, one Russian melodic hip-hop vocal theme and one female-vocal melodic house theme. tempo, key, meter, exact instrumentation and arrangement are left open. automatic choices can repeat and do not guarantee novelty; the vocal profiles still use fixed original lyrics. `segment_seconds` remains the duration for stations without profiles. generation refills below 30 minutes and stops at 60 minutes of ready audio per station. the scheduler selects the least-buffered station that needs refilling.

adding a station means adding a list entry, redeploying the generator, waiting for its fallback and queue to fill, then redeploying radio. add its `/streams/<id>.mp3` url to the client. station changes are not hot-reloaded. removing a station does not delete its files; remove obsolete data manually when desired.

one ACE-Step XL turbo (4B DiT) model and its 4B music language model stay loaded across jobs, with 8-bit DiT weight quantization and CPU offloading for the RTX 3060 12GB. each call generates an entire instrumental song (8 inference steps, shift 3.0), with no independently generated short segments. temporary model outputs are removed after success or failure. ffmpeg normalizes to -16 lufs / -1.5 dbtp, 48 khz stereo flac before atomic publication. liquidsoap encodes the broadcast as 192 kbps mp3.

## provisioning another host

1. install a compatible nvidia driver and nvidia container toolkit, configure docker's nvidia runtime, and verify container gpu access. cuda 12.8 compatibility must be checked on the actual host. use a lord build containing [gpu passthrough support](https://github.com/schmidthole/lord/pull/3).
2. update `server` and `sshkeyfile` in both lord configs for the target host. update or remove the home-network port binding for the new host; loopback HTTP remains on port 8080. for public HTTPS instead, set `web: true`, remove `ports`, configure a real hostname and certificate email, and restore `webadvancedconfig: {writetimeout: 0}` for streaming. the default Traefik ACME setup does not support a LAN-only `.local` hostname.
3. copy `radio.env.example` to `radio.env` and replace both passwords with random values. this file is ignored by git and docker builds. both containers share `/srv/yogurt`; lord also provides separate `/data` mounts. runtime files use uid/gid 1000, with the entrypoints preparing ownership.
4. build the pinned runtime on the build host with `make ace-runtime`, then deploy:

   ```sh
   lord -config generator -deploy
   ```

   the generator downloads missing checkpoints on first initialization. `/data/checkpoints`
   persists under `/var/yogurt-generator/checkpoints` on the host. allow disk space and time
   for the initial downloads. to reuse existing audition checkpoints, copy them into this
   directory while the generator is stopped and set ownership to uid/gid 1000.

5. wait for generation to populate `/srv/yogurt/night-drive/ready` and `fallback/seed.flac`, then deploy radio:

   ```sh
   lord -config generator -logs
   lord -config radio -deploy
   ```

   the radio initializer rejects missing/undecodable fallback audio. allow the queue to fill before relying on unattended playback. the generator seeds the fallback from its first valid song; you can add more normalized flac files to that station's fallback directory for variety.
6. verify `https://radio.example.com/healthz`, add the stream url to radio, and listen. later, run a longer single-station soak on the real host with generator interruptions and restarts.

lord's `writetimeout: 0` setting applies to the host-wide traefik entrypoint. leave response buffering options unset. only the radio container joins traefik; internal icecast and queue endpoints bind to loopback. public routing allows only configured stream paths and `/healthz`. credentials and admin endpoints are not exposed through that router.

## queue and recovery

```text
/srv/yogurt/<station-id>/
  ready/       completed generated songs
  playing/     files claimed by liquidsoap
  fallback/    fixed backup library
```

the generator writes hidden temporary files and publishes only validated, completed audio. a filesystem lock prevents concurrent generators using the same directory. it stops producing at the buffer targets, reserves free disk space for temporary audio, and backs off on failures. ready-duration accounting deducts crossfade overlap and excludes currently claimed files conservatively. stored audio stays bounded by configured queue targets, small playout prefetch, and the fixed fallback library; there is no archive.

the go adapter atomically claims files in filename order. liquidsoap owns those files as temporary requests and deletes them after use, including invalid requests it cannot decode. each fresh liquidsoap process asks the adapter to recover leftover claims before requesting more audio. a hard crash can replay an interrupted song; graceful shutdown can discard prefetched temporary songs. these small losses/replays are acceptable for a live stream.

when ready audio runs out, liquidsoap loops the fallback library and resumes fresh audio at a track boundary. an output safety guard provides silence if the audio graph temporarily cannot supply samples. generator outages do not stop the radio. s6 restarts failed radio processes; docker restarts containers after host reboot. radio restarts or deployments can interrupt listeners, requiring reconnection. docker health status reports missing mountpoints but does not itself restart an unhealthy container.

```sh
lord -config generator -status
lord -config generator -logs
lord -config radio -status
lord -config radio -logs
```

stop the generator before deleting or replacing its data. keep fallback audio. recover persisted `playing` files through a radio restart, rather than moving files while liquidsoap is reading them. if generation fails repeatedly, inspect its logs, disk space, model files, and gpu runtime; fallback remains available.

## dependencies and validation boundary

runtime: the pinned ACE-Step source and its upstream dependency lock, liquidsoap 2.1.3,
icecast 2.4.4, s6-overlay 3.2.0.2, and go. `uv.lock` in this repository covers local test tools.
GPU model inference is separate from the CPU unit and radio integration tests.

The full-song audition on this RTX 3060 12GB produced 180–210 seconds of music in
51–58 seconds per track after model initialization. This is a measured sample, not a
throughput guarantee. The deployed fallback library uses complete tracks from the current dramatic lo-fi synthwave
profiles. The original auditions remain available separately; the original Magenta queue was
archived during migration. See
`scripts/ACE_STEP_AUDITIONS.md` for the reproducible audition workflow.

## model sizing and performance

The generator image selects `ACESTEP_DIT_MODEL=acestep-v15-xl-turbo`,
`ACESTEP_LM_MODEL=acestep-5Hz-lm-4B`, and `ACESTEP_QUANTIZATION=int8_weight_only`.
These environment variables can be overridden when launching the container. Supported
DiT choices are the standard and XL turbo models; language-model sizes are 0.6B, 1.7B,
and 4B. Quantization accepts `none` or `int8_weight_only`. CPU offloading stays enabled.
The standalone Python adapter retains the small audition configuration as its default;
the production Docker image explicitly selects the benchmarked larger models.

Run a full-song benchmark on an empty output directory:

```sh
./scripts/run-acestep-benchmark.sh acestep-v15-xl-turbo acestep-5Hz-lm-4B int8_weight_only \
  "$HOME/.cache/yogurt-benchmark-xl"
```

The script temporarily stops the live generator to free the GPU, uses an isolated audio
queue, and restores the live generator on exit. It measures generation plus normalization
for every configured profile after initialization. A candidate passes when every song takes
at most 80% of its usable playout time (duration minus crossfade). The benchmark has a
24GiB memory limit and a 28GiB combined memory/swap limit. It writes `results.json` alongside
the test audio; those files are not added to the live station automatically. Results apply
to this single-station workload, not to an arbitrary number of simultaneous stations.

Measured on this host: XL + 4B took 96.22s, 106.50s, and 92.56s for the three
180/210/180-second profiles, including normalization, after 65.66s initialization.
Peak allocated GPU tensor memory was 8.42GiB (not total driver-reported VRAM).
See `benchmarks/rtx3060.json` for the baseline comparison and individual results.

The local production generator also uses the benchmark's 24GiB memory and 28GiB
combined memory/swap limits. Lord does not currently encode these limits in its YAML;
after a Lord redeploy, reapply them on the Docker host:

```sh
docker update --memory 24g --memory-swap 28g yogurt-generator
```

The Night Drive mix includes three instrumental synthwave profiles, one Russian
melodic hip-hop profile and one English female-vocal melodic house profile. See [prompt research and vocal
configuration](scripts/RUSSIAN_HIPHOP.md). Song profiles may supply `lyrics` and
`vocal_language` (for example `ru`); omitted lyrics preserve instrumental output.

The house theme is the fifth selectable profile (20% expected share, with uniform
random selection). It uses original English lyrics and a 210-second duration,
with automatic tempo and key. See [house prompt research](scripts/MELODIC_HOUSE.md).
