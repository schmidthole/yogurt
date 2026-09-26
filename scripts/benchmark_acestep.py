"""Measure complete generation and normalization against actual playout duration."""

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import torch

from generator.acestep import AceStep
from generator.config import load_config
from generator.main import Generator


def main():
    """Benchmark each station profile once with one reused model instance."""
    config = load_config(Path("/app/stations.yml"))
    started = time.monotonic()
    backend = AceStep()
    initialization = time.monotonic() - started
    root = Path("/radio")
    results = []
    for index, song in enumerate(config.stations[0].songs):
        station = replace(config.stations[0], id=f"benchmark-{index}", songs=(song,))
        worker = Generator(replace(config, stations=(station,)), root, backend)
        worker.prepare()
        torch.cuda.reset_peak_memory_stats()
        started = time.monotonic()
        if not worker.step():
            raise RuntimeError("Expected generation into an empty benchmark queue")
        elapsed = time.monotonic() - started
        usable = song.seconds - config.crossfade_seconds
        result = dict(
            profile=index,
            duration_seconds=song.seconds,
            wall_seconds=round(elapsed, 2),
            playout_seconds=usable,
            realtime_factor=round(elapsed / usable, 3),
            peak_gpu_allocated_gib=round(torch.cuda.max_memory_allocated() / 2**30, 2),
        )
        results.append(result)
        print("BENCHMARK " + json.dumps(result), flush=True)
    report = dict(
        model=os.environ["ACESTEP_DIT_MODEL"],
        lm=os.environ["ACESTEP_LM_MODEL"],
        quantization=os.environ.get("ACESTEP_QUANTIZATION", "none"),
        initialization_seconds=round(initialization, 2),
        tracks=results,
        passes=all(r["realtime_factor"] <= 0.8 for r in results),
    )
    (root / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print("RESULT " + json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
