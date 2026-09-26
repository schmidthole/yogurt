import argparse
import fcntl
import logging
import math
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from generator.config import load_config

log = logging.getLogger(__name__)


def duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    seconds = float(result.stdout.strip())
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("invalid audio duration")
    return seconds


def normalize(source, destination):
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "flac",
            str(destination),
        ],
        check=True,
        capture_output=True,
        timeout=600,
    )


class Scheduler:
    def __init__(self, config):
        self.config = config
        self.refilling = set()

    def choose(self, levels):
        for station in self.config.stations:
            if levels[station.id] < self.config.buffer_low_seconds:
                self.refilling.add(station.id)
            if levels[station.id] >= self.config.buffer_target_seconds:
                self.refilling.discard(station.id)
        eligible = [s for s in self.config.stations if s.id in self.refilling]
        return min(eligible, key=lambda s: (levels[s.id], s.id), default=None)


class Generator:
    def __init__(self, config, root, backend, probe=duration, processor=normalize):
        self.config, self.root, self.backend = config, root, backend
        self.probe, self.processor = probe, processor
        self.scheduler = Scheduler(config)
        self.cache = {}

    def prepare(self):
        for station in self.config.stations:
            for folder in ("ready", "playing", "fallback"):
                (self.root / station.id / folder).mkdir(parents=True, exist_ok=True)
            for path in (self.root / station.id).glob(".generating-*"):
                if path.is_file():
                    path.unlink()

    def levels(self):
        levels = {}
        live = set()
        for station in self.config.stations:
            total = 0
            # exclude playing: its remaining duration is deliberately conservative
            for path in (self.root / station.id / "ready").glob("*.flac"):
                try:
                    stat = path.stat()
                    key = (path, stat.st_size, stat.st_mtime_ns)
                    live.add(key)
                    if key not in self.cache:
                        self.cache[key] = self.probe(path)
                    total += max(0, self.cache[key] - self.config.crossfade_seconds)
                except FileNotFoundError:
                    continue
                except (ValueError, subprocess.SubprocessError):
                    log.warning("invalid ready audio: %s", path.name)
                    path.unlink(missing_ok=True)
            levels[station.id] = total
        self.cache = {key: value for key, value in self.cache.items() if key in live}
        return levels

    def step(self):
        station = self.scheduler.choose(self.levels())
        if station is None:
            return False
        # reserve space for bounded raw and normalized temporary output
        reserve = self.config.segment_seconds * 48000 * 2 * 4 + 512 * 1024 * 1024
        if shutil.disk_usage(self.root).free < reserve:
            raise OSError("insufficient free disk space")
        identifier = f"{time.time_ns():020d}-{uuid.uuid4().hex}"
        folder = self.root / station.id
        raw = folder / f".generating-{identifier}.wav"
        processed = folder / f".generating-{identifier}.flac"
        try:
            self.backend.generate(station.prompt, self.config.segment_seconds, raw)
            self.processor(raw, processed)
            if abs(self.probe(processed) - self.config.segment_seconds) > 1:
                raise ValueError("unexpected generated duration")
            # make fallback available before publishing the first queue entry
            fallback = folder / "fallback" / "seed.flac"
            if not any((folder / "fallback").glob("*.flac")):
                temporary = folder / f".generating-{identifier}-fallback.flac"
                try:
                    shutil.copyfile(processed, temporary)
                    os.replace(temporary, fallback)
                finally:
                    temporary.unlink(missing_ok=True)
            os.replace(processed, folder / "ready" / f"{identifier}.flac")
            log.info("published segment for %s", station.id)
        finally:
            raw.unlink(missing_ok=True)
            processed.unlink(missing_ok=True)
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("/app/stations.yml"))
    parser.add_argument("--root", type=Path, default=Path("/radio"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = load_config(args.config)
    args.root.mkdir(parents=True, exist_ok=True)
    with (args.root / ".generator.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from generator.mrt import Magenta

        worker = Generator(config, args.root, Magenta())
        worker.prepare()
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        delay = 5
        while not stop.is_set():
            try:
                generated = worker.step()
                delay = 5
                stop.wait(0 if generated else 10)
            except Exception as error:
                log.error("generation failed: %s", str(error).lower())
                stop.wait(delay)
                delay = min(delay * 2, 300)


if __name__ == "__main__":
    main()
