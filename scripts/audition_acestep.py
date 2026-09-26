"""Generate complete, reproducible ACE-Step tracks outside the live radio queue."""
import json
import os
from pathlib import Path
import shutil
import time

TRACKS = [
    ("01-neon-highway", 100, "A minor", 180,
     "Instrumental synthwave, 100 BPM, A minor. A memorable warm analog synth lead melody, "
     "pulsing eighth-note bass, tight electronic kick and snare, shimmering arpeggios. "
     "Full song: atmospheric intro, melodic main theme, contrasting quiet breakdown, "
     "energetic return of the theme, resolved outro. Clear balanced studio production."),
    ("02-after-hours", 85, "D minor", 210,
     "Instrumental downtempo electronic track, 85 BPM, D minor. Warm electric piano chords, "
     "melodic analog bass, crisp relaxed drum groove, spacious lead synthesizer. "
     "Full song with a short intro, evolving memorable theme, contrasting bridge, "
     "return to the main groove and gentle ending. Intimate late night mood, clean mix."),
    ("03-city-lights", 118, "C minor", 180,
     "Instrumental melodic synthwave, 118 BPM, C minor. Driving drum machine groove, "
     "rubbery synth bass, bright repeating arpeggio and expressive soaring lead melody. "
     "Complete arrangement with intro, main hook, stripped-back middle section, "
     "final full-band hook and a deliberate outro. Punchy polished electronic production."),
]


def main():
    """Load memory-conscious models once and save songs plus generation metadata."""
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music

    output = Path(os.environ.get("AUDITION_OUTPUT", "/output"))
    output.mkdir(parents=True, exist_ok=True)
    dit = AceStepHandler()
    status, ok = dit.initialize_service(
        project_root="/app", config_path="acestep-v15-turbo", device="cuda",
        offload_to_cpu=True, offload_dit_to_cpu=True,
    )
    if not ok:
        raise RuntimeError(status)
    lm = LLMHandler()
    status, ok = lm.initialize(
        checkpoint_dir="/app/checkpoints", lm_model_path="acestep-5Hz-lm-0.6B",
        backend="pt", device="cuda", offload_to_cpu=True,
    )
    if not ok:
        raise RuntimeError(status)
    for index, (name, bpm, key, seconds, caption) in enumerate(TRACKS):
        destination = output / f"{name}.flac"
        if destination.exists():
            continue
        seed = 260926 + index
        params = GenerationParams(
            caption=caption, lyrics="[Instrumental]", instrumental=True,
            bpm=bpm, keyscale=key, timesignature="4", duration=seconds,
            inference_steps=8, shift=3.0, seed=seed, thinking=True,
            use_cot_caption=False, use_cot_metas=False,
        )
        config = GenerationConfig(
            batch_size=1, audio_format="flac", use_random_seed=False, seeds=[seed],
        )
        started = time.monotonic()
        result = generate_music(dit, lm, params, config, save_dir=str(output / "raw"))
        if not result.success or not result.audios:
            raise RuntimeError(result.error or "No generated audio")
        shutil.copyfile(result.audios[0]["path"], destination)
        metadata = {
            "title": name, "caption": caption, "bpm": bpm, "key": key,
            "duration_seconds": seconds, "seed": seed, "model": "acestep-v15-turbo",
            "lm": "acestep-5Hz-lm-0.6B", "elapsed_seconds": time.monotonic() - started,
            "source_revision": os.environ.get("ACESTEP_REVISION", "unknown"),
        }
        destination.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata), flush=True)


if __name__ == "__main__":
    main()
