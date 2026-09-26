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

    def test_invalid_song_profiles_rejected(self):
        import copy

        import yaml

        original = yaml.safe_load(Path("stations.yml").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stations.yml"
            for field, value in (
                ("seconds", 481),
                ("seconds", True),
                ("bpm", 0),
                ("key", ""),
            ):
                bad = copy.deepcopy(original)
                bad["stations"][0]["songs"][0][field] = value
                path.write_text(yaml.safe_dump(bad))
                with self.assertRaises(ValueError):
                    load_config(path)


class AceStepAdapterTests(unittest.TestCase):
    def test_full_songs_reuse_models_and_cleanup_outputs(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from generator.acestep import AceStep

        dit, lm = MagicMock(), MagicMock()
        dit.initialize_service.return_value = ("ready", True)
        lm.initialize.return_value = ("ready", True)
        output_dirs = []

        def generate(*args, save_dir):
            output_dirs.append(Path(save_dir))
            path = Path(save_dir) / "song.wav"
            path.write_bytes(b"complete song")
            return SimpleNamespace(
                success=True, audios=[{"path": str(path)}], error=None
            )

        generate_mock = MagicMock(side_effect=generate)
        with (
            patch.dict(
                sys.modules,
                {
                    "torch": SimpleNamespace(
                        cuda=SimpleNamespace(is_available=lambda: True)
                    ),
                    "acestep.handler": SimpleNamespace(AceStepHandler=lambda: dit),
                    "acestep.llm_inference": SimpleNamespace(LLMHandler=lambda: lm),
                    "acestep.inference": SimpleNamespace(
                        GenerationParams=SimpleNamespace,
                        GenerationConfig=SimpleNamespace,
                        generate_music=generate_mock,
                    ),
                },
            ),
            patch.dict(
                "os.environ",
                {
                    "ACESTEP_DIT_MODEL": "acestep-v15-xl-turbo",
                    "ACESTEP_LM_MODEL": "acestep-5Hz-lm-4B",
                    "ACESTEP_QUANTIZATION": "int8_weight_only",
                },
            ),
            tempfile.TemporaryDirectory() as directory,
        ):
            backend = AceStep()
            for index in range(2):
                destination = Path(directory) / f"{index}.wav"
                backend.generate("synthwave", 180, destination, bpm=100, key="A minor")
                self.assertEqual(destination.read_bytes(), b"complete song")
            self.assertEqual(dit.initialize_service.call_count, 1)
            self.assertEqual(lm.initialize.call_count, 1)
            self.assertEqual(
                dit.initialize_service.call_args.kwargs["config_path"],
                "acestep-v15-xl-turbo",
            )
            self.assertEqual(
                dit.initialize_service.call_args.kwargs["quantization"],
                "int8_weight_only",
            )
            self.assertEqual(
                lm.initialize.call_args.kwargs["lm_model_path"], "acestep-5Hz-lm-4B"
            )
            with patch.dict("os.environ", {"ACESTEP_DIT_MODEL": "not-a-model"}):
                with self.assertRaisesRegex(ValueError, "unsupported turbo model"):
                    AceStep()
            params = generate_mock.call_args.args[2]
            self.assertEqual(
                (params.duration, params.bpm, params.shift), (180, 100, 3.0)
            )
            self.assertTrue(params.instrumental)
            self.assertTrue(generate_mock.call_args.args[3].use_random_seed)
            self.assertFalse(any(p.exists() for p in output_dirs))
            generate_mock.side_effect = lambda *a, **kw: SimpleNamespace(
                success=False, audios=[], error="inference failed"
            )
            with self.assertRaisesRegex(RuntimeError, "inference failed"):
                backend.generate("synthwave", 180, Path(directory) / "failed.wav")
            self.assertFalse((Path(directory) / "failed.wav").exists())

    def test_song_profile_controls_and_duration_validation(self):
        from dataclasses import replace
        from unittest.mock import MagicMock

        from generator.config import Song

        song = Song("full song", 210, 85, "D minor")
        cfg = replace(config(), stations=(Station("one", "one", "ambient", (song,)),))
        with tempfile.TemporaryDirectory() as directory:
            backend = MagicMock()
            backend.generate.side_effect = (
                lambda prompt, seconds, path, **kw: path.write_bytes(b"audio")
            )
            worker = Generator(
                cfg, Path(directory), backend, lambda _: 210, shutil.copyfile
            )
            worker.prepare()
            self.assertTrue(worker.step())
            self.assertEqual(backend.generate.call_args.args[:2], ("full song", 210))
            self.assertEqual(
                backend.generate.call_args.kwargs, {"bpm": 85, "key": "D minor"}
            )
            self.assertEqual(worker.levels(), {"one": 209})


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
