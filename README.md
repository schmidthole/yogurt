# yogurt

self-hosted ai radio: one gpu generator and one radio container, deployed with lord. the initial configuration broadcasts one station; additional stations share the same model and have independent queues and icecast mountpoints.

```text
magenta realtime 2 -> normalized flac queues -> liquidsoap -> icecast
                                                               |
                                                  go stream proxy :80
                                                               |
                                                          traefik
                                                               |
                                                    radio macos app
```

there is no web player, catalog api, database, or benchmark suite. add this url in [radio](https://github.com/pom11/Radio) settings after deployment:

```text
https://radio.example.com/streams/night-drive.mp3
```

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
make generator
```

`make generator` builds for linux/amd64 with pinned python dependencies, including cuda 13 jax. it is a large image and needs no gpu at build time. the model itself is downloaded separately on the host; it is not baked into the image. the radio build supports amd64 and arm64.

## station configuration

edit `stations.yml`. ids must be unique lowercase slugs. each station has a name and prompt. segments default to 180 seconds with five-second crossfades. generation refills below 30 minutes and stops at 60 minutes of ready audio per station. the scheduler selects the least-buffered station that needs refilling.

adding a station means adding a list entry, redeploying the generator, waiting for its fallback and queue to fill, then redeploying radio. add its `/streams/<id>.mp3` url to the client. station changes are not hot-reloaded. removing a station does not delete its files; remove obsolete data manually when desired.

one magenta model stays loaded across all generation jobs. generation runs in four-second chunks with context carried within a segment and reset between segments, preventing station context from mixing. ffmpeg normalizes to -16 lufs / -1.5 dbtp, 48 khz stereo flac before atomic publication. liquidsoap encodes the broadcast as 192 kbps mp3.

## deploy when the linux gpu host is available

1. install a compatible nvidia driver and nvidia container toolkit, configure docker's nvidia runtime, and verify container gpu access. cuda 13 compatibility must be checked on the actual host. use a lord build containing [gpu passthrough support](https://github.com/schmidthole/lord/pull/3).
2. fill in `server`, ssh settings if needed, and radio hostname/email in both lord configs. use a hostname and acme http-challenge setup supported by lord. a lan-only `.local` name does not work with its default certificate setup. restrict external reachability at the host/router if the radio is intended for a private network.
3. copy `radio.env.example` to `radio.env` and replace both passwords with random values. this file is ignored by git and docker builds. both containers share `/srv/yogurt`; lord also provides separate `/data` mounts. runtime files use uid/gid 1000, with the entrypoints preparing ownership.
4. deploy the generator image:

   ```sh
   lord -config generator -deploy
   ```

   on the first deployment it will restart until its model assets exist. on the linux host, stop it while downloading the assets into its persistent data directory:

   ```sh
   sudo docker stop yogurt-generator
   sudo docker run --rm \
     -v /var/yogurt-generator:/data \
     lorddirect/yogurt-generator:latest \
     sh -c 'mrt models init && mrt checkpoints download mrt2_small'
   sudo docker start yogurt-generator
   ```

   these commands assume the provided registry-less lord configuration. if using a registry, substitute its image tag. jax needs the raw checkpoint (`mrt checkpoints download`), not the exported mlx model. the shared resources and checkpoint live under `/data/magenta/magenta-rt-v2`.
5. wait for generation to populate `/srv/yogurt/night-drive/ready` and `fallback/seed.flac`, then deploy radio:

   ```sh
   lord -config generator -logs
   lord -config radio -deploy
   ```

   the radio initializer rejects missing/undecodable fallback audio. allow the queue to fill before relying on unattended playback. the generator seeds the fallback from its first valid segment; you can add more normalized flac files to that station's fallback directory for variety.
6. verify `https://radio.example.com/healthz`, add the stream url to radio, and listen. later, run a longer single-station soak on the real host with generator interruptions and restarts.

lord's `writetimeout: 0` setting applies to the host-wide traefik entrypoint. leave response buffering options unset. only the radio container joins traefik; internal icecast and queue endpoints bind to loopback. public routing allows only configured stream paths and `/healthz`. credentials and admin endpoints are not exposed through that router.

## queue and recovery

```text
/srv/yogurt/<station-id>/
  ready/       completed generated segments
  playing/     files claimed by liquidsoap
  fallback/    fixed backup library
```

the generator writes hidden temporary files and publishes only validated, completed audio. a filesystem lock prevents concurrent generators using the same directory. it stops producing at the buffer targets, reserves free disk space for temporary audio, and backs off on failures. ready-duration accounting deducts crossfade overlap and excludes currently claimed files conservatively. stored audio stays bounded by configured queue targets, small playout prefetch, and the fixed fallback library; there is no archive.

the go adapter atomically claims files in filename order. liquidsoap owns those files as temporary requests and deletes them after use, including invalid requests it cannot decode. each fresh liquidsoap process asks the adapter to recover leftover claims before requesting more audio. a hard crash can replay an interrupted segment; graceful shutdown can discard prefetched temporary segments. these small losses/replays are acceptable for a live stream.

when ready audio runs out, liquidsoap loops the fallback library and resumes fresh audio at a track boundary. an output safety guard provides silence if the audio graph temporarily cannot supply samples. generator outages do not stop the radio. s6 restarts failed radio processes; docker restarts containers after host reboot. radio restarts or deployments can interrupt listeners, requiring reconnection. docker health status reports missing mountpoints but does not itself restart an unhealthy container.

```sh
lord -config generator -status
lord -config generator -logs
lord -config radio -status
lord -config radio -logs
```

stop the generator before deleting or replacing its data. keep fallback audio. recover persisted `playing` files through a radio restart, rather than moving files while liquidsoap is reading them. if generation fails repeatedly, inspect its logs, disk space, model files, and gpu runtime; fallback remains available.

## dependencies and validation boundary

runtime: python 3.12, magenta-rt 2.0.3, jax 0.10.1/cuda 13, liquidsoap 2.1.3, icecast 2.4.4, s6-overlay 3.2.0.2, and go. `uv.lock` covers local tools; `generator/requirements.txt` pins the linux inference environment. regenerate it with:

```sh
uv pip compile generator/requirements.in --python-version 3.12 \
  --python-platform x86_64-manylinux_2_36 --no-annotate --no-header \
  -o generator/requirements.txt
```

local cpu tests do not establish gpu inference compatibility, sustained generation on the future host, traefik behavior on that host, or playback in the installed radio macos app. those checks remain for deployment. there is no throughput benchmark requirement.

validated locally on 2026-09-25: formatting, python unit tests, go race tests, cpu-container audio tests, two-station radio integration, both image builds, and dependency/import checks in the linux/amd64 generator image. model weights were not downloaded and gpu inference was not run. the lord pr also passes its go unit tests.
