# Full-song auditions

This experiment generates three complete instrumental songs outside the live radio queue.
The station continues playing buffered tracks while the audition process uses the GPU.
Listen to the results before selecting a replacement generator; technical audio validity is not
an assessment of musical quality.

## Runtime

Official source: https://github.com/ace-step/ACE-Step-1.5
Pinned revision: `ca1e85fe9430179831e6bc6be790c332190a3866`

Build the upstream Dockerfile from that revision:

```sh
git clone https://github.com/ace-step/ACE-Step-1.5.git ~/src/ACE-Step-1.5
git -C ~/src/ACE-Step-1.5 checkout ca1e85fe9430179831e6bc6be790c332190a3866
docker build -t yogurt-acestep:audition ~/src/ACE-Step-1.5
```

Model weights persist in `~/.local/share/yogurt-acestep/checkpoints`. Initialization downloads
missing assets. The generator uses the standard 2B turbo model and the 0.6B music language
model, batch size one, with CPU offloading for the RTX 3060 12GB.

## Generate

```sh
./scripts/run-acestep-auditions.sh
```

The script temporarily stops `yogurt-generator` to free GPU memory and restores it on exit.
The radio container remains running. Do not run multiple audition jobs simultaneously.
Outputs are in `~/Music/yogurt-auditions`: FLAC songs, JSON generation settings and timings,
and original model outputs in `raw/`. Existing completed FLAC files are skipped on reruns.
The three prompts use 85, 100, and 118 BPM and request complete arrangements with endings.

The production backend now uses the larger benchmarked XL/4B configuration; this script retains the original smaller audition settings. `stations.yml` now holds three dramatic lo-fi synthwave soundscape
profiles; production varies the seed for each complete song and publishes it
through the existing normalization and atomic queue. The audition runner remains separate
and does not publish its outputs to the station. Its GPU use temporarily pauses production.
