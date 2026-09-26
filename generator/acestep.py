"""Generate complete songs with a configurable, memory-conscious ACE-Step runtime."""

import logging
import os
import shutil
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


class AceStep:
    def __init__(self):
        import torch
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler

        if not torch.cuda.is_available():
            raise RuntimeError("a cuda gpu is required")
        checkpoints = os.environ.get("ACESTEP_CHECKPOINTS_DIR", "/data/checkpoints")
        model = os.environ.get("ACESTEP_DIT_MODEL", "acestep-v15-turbo")
        language_model = os.environ.get("ACESTEP_LM_MODEL", "acestep-5Hz-lm-0.6B")
        quantization = os.environ.get("ACESTEP_QUANTIZATION", "none")
        if model not in {"acestep-v15-turbo", "acestep-v15-xl-turbo"}:
            raise ValueError("unsupported turbo model")
        if language_model not in {
            f"acestep-5Hz-lm-{size}" for size in ("0.6B", "1.7B", "4B")
        }:
            raise ValueError("unsupported music language model")
        if quantization not in {"none", "int8_weight_only"}:
            raise ValueError("unsupported quantization")
        log.info(
            "ACE-Step model=%s language_model=%s quantization=%s",
            model,
            language_model,
            quantization,
        )
        self.dit = AceStepHandler()
        status, ok = self.dit.initialize_service(
            project_root="/app",
            config_path=model,
            quantization=None if quantization == "none" else quantization,
            device="cuda",
            offload_to_cpu=True,
            offload_dit_to_cpu=True,
        )
        if not ok:
            raise RuntimeError(status)
        self.lm = LLMHandler()
        status, ok = self.lm.initialize(
            checkpoint_dir=checkpoints,
            lm_model_path=language_model,
            backend="pt",
            device="cuda",
            offload_to_cpu=True,
        )
        if not ok:
            raise RuntimeError(status)

    def generate(self, prompt, seconds, destination, *, bpm=None, key=""):
        from acestep.inference import GenerationConfig, GenerationParams, generate_music

        params = GenerationParams(
            caption=prompt,
            lyrics="[Instrumental]",
            instrumental=True,
            bpm=bpm,
            keyscale=key,
            timesignature="4",
            duration=seconds,
            inference_steps=8,
            shift=3.0,
            thinking=True,
            use_cot_caption=False,
            use_cot_metas=False,
        )
        config = GenerationConfig(
            batch_size=1, audio_format="wav", use_random_seed=True
        )
        # TemporaryDirectory also removes ACE-Step sidecars and failed partial outputs.
        with tempfile.TemporaryDirectory(prefix="acestep-") as temporary:
            result = generate_music(
                self.dit, self.lm, params, config, save_dir=temporary
            )
            if not result.success or len(result.audios) != 1:
                raise RuntimeError(result.error or "expected one complete song")
            source = Path(result.audios[0]["path"])
            if not source.is_file():
                raise RuntimeError("ACE-Step returned no audio file")
            shutil.copyfile(source, destination)
            log.info("generated song: %ss, bpm=%s, key=%s", seconds, bpm, key)
