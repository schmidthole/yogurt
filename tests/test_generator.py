import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from generator.config import Config, Station, load_config
from generator.main import Generator, Scheduler


def config():
    return Config(
        (Station("one", "one", "ambient"), Station("two", "two", "jazz")), 10, 1, 20, 30
    )


class FakeModel:
    def generate(self, prompt, seconds, path):
        path.write_bytes(b"audio")


class GeneratorTests(unittest.TestCase):
    def test_refill_hysteresis_and_fairness(self):
        scheduler = Scheduler(config())
        self.assertEqual(scheduler.choose({"one": 10, "two": 5}).id, "two")
        self.assertEqual(scheduler.choose({"one": 10, "two": 25}).id, "one")
        self.assertEqual(scheduler.choose({"one": 25, "two": 30}).id, "one")
        self.assertIsNone(scheduler.choose({"one": 30, "two": 30}))
        self.assertIsNone(scheduler.choose({"one": 22, "two": 22}))

    def test_publication_fallback_cleanup_and_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = Generator(
                config(), root, FakeModel(), lambda _: 10, shutil.copyfile
            )
            worker.prepare()
            stale = root / "one/.generating-stale.wav"
            stale.touch()
            worker.prepare()
            self.assertFalse(stale.exists())
            self.assertTrue(worker.step())
            self.assertEqual(worker.levels(), {"one": 9, "two": 0})
            self.assertEqual(len(list((root / "one/ready").glob("*.flac"))), 1)
            self.assertTrue((root / "one/fallback/seed.flac").exists())
            self.assertFalse(list(root.glob("*/.generating-*")))
            self.assertTrue(worker.step())
            self.assertEqual(worker.levels(), {"one": 9, "two": 9})

    def test_failed_processing_never_publishes(self):
        def fail(*_):
            raise RuntimeError("failed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = Generator(config(), root, FakeModel(), lambda _: 10, fail)
            worker.prepare()
            with self.assertRaises(RuntimeError):
                worker.step()
            self.assertFalse(list(root.glob("*/ready/*")))
            self.assertFalse(list(root.glob("*/.generating-*")))

    def test_invalid_ready_audio_removed_and_playing_ignored(self):
        def probe(_):
            raise ValueError("bad audio")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = Generator(config(), root, FakeModel(), probe, shutil.copyfile)
            worker.prepare()
            (root / "one/ready/bad.flac").touch()
            (root / "one/playing/active.flac").touch()
            self.assertEqual(worker.levels(), {"one": 0, "two": 0})
            self.assertFalse((root / "one/ready/bad.flac").exists())
            self.assertTrue((root / "one/playing/active.flac").exists())

    def test_no_generation_with_full_buffers_or_full_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Generator(config(), Path(directory), FakeModel())
            worker.prepare()
            with patch.object(worker, "levels", return_value={"one": 30, "two": 30}):
                self.assertFalse(worker.step())
            with patch("generator.main.shutil.disk_usage") as usage:
                usage.return_value.free = 0
                with self.assertRaises(OSError):
                    worker.step()

    def test_validation(self):
        original = Path("stations.yml").read_text()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stations.yml"
            path.write_text(original)
            self.assertEqual(load_config(path).stations[0].id, "night-drive")
            for bad in (
                original.replace("night-drive", "../escape"),
                original.replace("segment_seconds: 180", "segment_seconds: -1"),
                original.replace("crossfade_seconds: 5", "crossfade_seconds: 100"),
                original.replace(
                    "buffer_target_seconds: 3600", "buffer_target_seconds: 1"
                ),
                original + "unknown: true\n",
                original
                + "  - id: night-drive\n    name: duplicate\n    prompt: jazz\n",
            ):
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    load_config(path)


class MagentaAdapterTests(unittest.TestCase):
    def test_model_reuse_and_segment_context_isolation(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from generator.mrt import Magenta

        model = MagicMock()
        model.embed_style.return_value = "embedding"
        model.generate.side_effect = [
            (SimpleNamespace(samples="audio"), f"state-{index}") for index in range(6)
        ]
        factory = MagicMock(return_value=model)
        writer = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "jax": SimpleNamespace(
                    devices=lambda: [SimpleNamespace(platform="gpu")]
                ),
                "magenta_rt": SimpleNamespace(MagentaRT2Jax=factory),
                "soundfile": SimpleNamespace(SoundFile=writer),
            },
        ):
            backend = Magenta()
            backend.generate("ambient", 10, Path("first.wav"))
            backend.generate("ambient", 10, Path("second.wav"))
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(model.embed_style.call_count, 1)
        calls = model.generate.call_args_list
        self.assertIsNone(calls[0].kwargs["state"])
        self.assertEqual(calls[1].kwargs["state"], "state-0")
        self.assertIsNone(calls[3].kwargs["state"])
        self.assertEqual(sum(c.kwargs["frames"] for c in calls[:3]), 250)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "requires ffmpeg and ffprobe; run make test-audio",
)
class AudioTests(unittest.TestCase):
    def test_real_normalization_publication_and_fallback(self):
        import wave

        from generator.main import duration

        class Tone:
            def generate(self, prompt, seconds, destination):
                import math
                import struct

                with wave.open(str(destination), "wb") as output:
                    output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                    output.writeframes(
                        b"".join(
                            struct.pack(
                                "<h", int(4000 * math.sin(i * 2 * math.pi * 440 / 8000))
                            )
                            for i in range(seconds * 8000)
                        )
                    )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = Generator(config(), root, Tone())
            worker.prepare()
            worker.step()
            ready = next((root / "one/ready").glob("*.flac"))
            self.assertAlmostEqual(duration(ready), 10, places=1)
            self.assertEqual(
                ready.read_bytes(), (root / "one/fallback/seed.flac").read_bytes()
            )


if __name__ == "__main__":
    unittest.main()
