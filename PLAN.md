# yogurt implementation plan

status: implemented locally; gpu inference, host deployment, client playback, and a longer reliability soak remain for the future linux machine. see README.md for commands and validation boundaries. lord gpu support is proposed in https://github.com/schmidthole/lord/pull/3.

## architecture

follow the final deployment architecture in the [shared conversation](https://chatgpt.com/share/6ab5d2f5-1ebc-83ea-975f-ebfb1a4221a7): two application containers on one linux gpu host, deployed independently with lord.

```text
yogurt-generator
  python + magenta realtime 2 small + jax/cuda
  one resident model, one scheduler for all stations
       |
       | shared host directory: /srv/yogurt
       v
yogurt-radio
  liquidsoap -> icecast on loopback
                   ^
                   | stream proxy
  small go http server on :80
  stream routing + internal queue adapter
       ^
       |
  lord-managed traefik -> radio macos client
```

use s6-overlay to supervise the three radio processes. keep the generator separate so its failures and deployments do not interrupt buffered playback. no additional reverse proxy inside the radio container: the go standard library proxies only the public stream paths to icecast and hosts the internal queue adapter. no web player or catalog service is needed.

liquidsoap owns transitions, fallback selection, and mp3 encoding. icecast owns listener distribution and mountpoints. these are established capabilities; yogurt should not implement an audio streaming engine. see the [liquidsoap quickstart](https://www.liquidsoap.info/doc-dev/quick_start) and [icecast setup documentation](https://www.icecast.org/docs/icecast-trunk/basic_setup/).

## minimal first version

- a list of configured stations, each with a stable id, display name, and one prompt; ship with exactly one station enabled.
- one model and one sequential generation worker shared by all stations.
- one yaml configuration, loaded at startup; configuration changes require redeployment.
- one mp3 stream per station, initially 192 kbps stereo.
- filesystem queues and a small, fixed fallback library per station.
- the existing radio macos menu-bar app as the client, with stations added by direct stream url.
- independent station queues and mountpoints so additional stations require configuration, not architectural changes.

defer web players, json/m3u catalogs, prompt variants, artwork, custom native apps, pwa installation, client-specific integrations, now-playing/history endpoints, accounts, administrative ui, live configuration, additional codecs, and listener-aware generation. no database, message broker, orchestration service, or llm station programmer.

the service is continuously available music, with repeated fallback material during generation outages. fallback also covers periods when generation cannot keep up. no benchmark suite or throughput qualification phase is planned. listeners joining a station hear its current broadcast; switching stations does not start another inference job.

## public interface

| path | purpose |
| --- | --- |
| `/streams/<id>.mp3` | continuous station audio |
| `/healthz` | basic radio readiness |

the [radio client](https://github.com/pom11/Radio) supports adding direct stream urls and playing icecast/mp3 streams. document each configured station's url in the deployment instructions, then add it through radio settings. no discovery protocol or catalog endpoint is required. derive playout configuration from the station list. restrict station ids to safe lowercase slugs. keep icecast administration, source authentication, and internal queue controls off public routes.

## implementation order

### 1. implement single-station generation

build the generator container with `mrt2_small` and one resident model. magenta documents linux/nvidia through its jax batch path, which fits buffered generation; see its [installation guide](https://raw.githubusercontent.com/magenta/magenta-realtime/main/docs/installation.md). start with 180-second segments and a short crossfade.

load stations as a list from the outset, but enable only the initial station. retain a simple least-buffered-station selection loop so the same worker can serve additional stations later. do not add benchmarking, performance reports, or station-capacity gates.

**done when:** the container generates valid, playable audio for the configured prompt and can generate subsequent segments without reloading the model. this is a functional smoke test, not a benchmark.

### 2. prove radio playback with fixture audio

assemble the radio container with pinned component versions, one liquidsoap process, one icecast process, the go server, and supervision. use fixture audio for playback tests. include a two-station integration case to check distinct mountpoints and switching, while the deployed configuration remains one station.

configure loopback-only icecast access inside the container. proxy streams without response buffering or a finite response-write deadline. validate mp3 support in the selected liquidsoap build. test crossfades and fallback-to-fresh transitions with actual audio.

**done when:** the radio macos client can listen, switch between fixture stations, and remain connected across many segment boundaries. killing and restarting a supervised child process recovers the service; radio restarts may require clients to reconnect.

### 3. connect the persistent filesystem queue

mount `/srv/yogurt:/radio` into both containers, leaving lord's automatic per-container `/data` mount available for private state such as the model cache.

```text
/radio/<station-id>/
  ready/
  playing/
  fallback/
```

the generator writes temporary audio on the same filesystem, normalizes it with ffmpeg, validates it, and atomically renames completed segments into `ready`. filenames carry ordering; obtain durations from audio metadata. start with a 30-minute refill threshold and a 60-minute target per station. always prioritize the station with the least playable time, and stop generating when all targets are met.

make ownership explicit: the generator publishes ready files; the radio side claims them by atomic rename into `playing`. use a small local queue adapter in the existing go process for liquidsoap's next-file requests. release/delete a claimed file only after liquidsoap no longer needs it, including prefetch and crossfade use. validate that lifecycle against the pinned liquidsoap version before finalizing the adapter.

on radio startup, recover leftover claimed files for replay. replaying one interrupted segment after a crash is acceptable; an exactly-once playback ledger is unnecessary. ignore and clean abandoned generation temporaries on generator startup. quarantine or remove invalid generated files with a logged reason so one bad segment cannot stall a station. never delete fallback files as queue cleanup.

seed valid fallback audio before declaring a station ready. when fresh audio runs out, loop fallback; resume fresh audio at a suitable boundary. bound queue storage and temporary output, retain no archive, and back off on generation or disk errors. model assets persist across deployments and are provisioned before normal operation.

**done when:** queues refill fairly, files are consumed without races, disk use stays bounded, and generator failure or restart leaves radio playback running.

### 4. make the narrow lord update

add optional `gpus: all`, emitting `--gpus all` only when configured. initially accept only omitted or `all`; reject unsupported values. update config examples and add tests for parsing, validation, and command construction. avoid arbitrary docker argument passthrough.

no `networks` extension is needed: the generator communicates through the shared directory, and the radio processes communicate over loopback. current lord already supports [build targets and volumes](https://raw.githubusercontent.com/schmidthole/lord/main/config.go), [web routing to port 80](https://raw.githubusercontent.com/schmidthole/lord/main/remote.go), and [zero/unlimited write timeouts](https://raw.githubusercontent.com/schmidthole/lord/main/traefik.go).

keep nvidia driver and [container toolkit setup](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) as documented host prerequisites. verify gpu access after docker/lord host setup; do not expand lord into a gpu provisioning tool.

**done when:** existing non-gpu deployments retain their behavior, tests pass, and a deployed generator container sees the target gpu.

### 5. package, deploy, and soak-test

use one root `Dockerfile` with `generator` and `radio` targets, plus `generator.lord.yml` and `radio.lord.yml`. use unique app names and the same shared-directory mount. store source/admin credentials in deployment environment files excluded from version control. establish shared-directory ownership for the actual container users.

set `web: true` only for radio. set `webadvancedconfig.writetimeout: 0` and leave buffering options unset. this timeout is host-wide in lord; verify the effective traefik configuration. use one hostname. decide the deployment hostname and certificate arrangement before deployment: lord's current web setup uses acme http validation, so a lan-only `.local` name does not fit its default tls path.

prefill queues and fallback audio, then deploy the radio container. document the two lord commands and basic restart/recovery procedures. run a single-station reliability soak, exercising generator loss, empty queues, malformed files, child-process failure, and container restart. verify stream continuity during generator loss and recovery after radio restart; zero-downtime radio deployment is outside this version.

**done when:** streams stay playable, queue levels recover under normal load, disk growth stops at the intended bounds, and service recovery does not need manual file repair.

## repository and validation

keep a small layout: `generator/`, `radio/`, `stations.yml`, a root `Dockerfile`, two lord configs, `Makefile`, and `README.md`. add files only as their implementation step needs them.

unit-test scheduler fairness and refill behavior, publication/recovery/cleanup, station validation, independent station queues/mountpoints, and proxy routing. use a fake generator for ordinary tests so they need no gpu or downloaded model. add container integration checks for the real liquidsoap file lifecycle, streaming, and fallback behavior. the smoke test and reliability soak verify operation; no hardware throughput benchmark is required.

provide `make fmt` and `make test`; format python with ruff and go with gofmt. run applicable unit tests after each implementation block. keep authored comments and logging messages lowercase. local formatting and cpu tests accompany the implementation.

when preparing deployment, supply the linux/gpu runtime details, ssh target, hostname/network exposure, and initial station prompt. these details do not change the proposed two-container structure.
