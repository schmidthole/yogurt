from pathlib import Path


class Magenta:
    def __init__(self):
        import jax
        from magenta_rt import MagentaRT2Jax

        if not any(device.platform == "gpu" for device in jax.devices()):
            raise RuntimeError("a cuda gpu is required")
        self.model = MagentaRT2Jax(size="mrt2_small")
        self.embeddings = {}

    def generate(self, prompt: str, seconds: int, destination: Path):
        import soundfile

        if prompt not in self.embeddings:
            self.embeddings[prompt] = self.model.embed_style(prompt, use_mapper=True)
        state = None
        # keep one segment's context; reset between segments and stations
        with soundfile.SoundFile(
            destination, mode="w", samplerate=48000, channels=2, subtype="PCM_16"
        ) as output:
            for offset in range(0, seconds, 4):
                waveform, state = self.model.generate(
                    conditioning={"musiccoca": self.embeddings[prompt]},
                    frames=min(4, seconds - offset) * 25,
                    state=state,
                )
                output.write(waveform.samples)
