"""exercise real playout and recovery without a gpu or model downloads."""

import array
import contextlib
import json
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import yaml


def docker(*args, **kwargs):
    return subprocess.run(
        ["docker", *args], check=True, text=True, capture_output=True, **kwargs
    ).stdout.strip()


def wait_for(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.5)
    raise AssertionError("timed out waiting for radio")


def main():
    name = "yogurt-test-" + uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix="yogurt-radio-") as directory:
        root = Path(directory)
        data = root / "data"
        data.mkdir()
        for station in ("one", "two"):
            for folder in ("ready", "playing", "fallback"):
                (data / station / folder).mkdir(parents=True)
        config = {
            "segment_seconds": 10,
            "crossfade_seconds": 1,
            "buffer_low_seconds": 20,
            "buffer_target_seconds": 30,
            "stations": [
                {"id": station, "name": station + ' #{literal} "', "prompt": "fixture"}
                for station in ("one", "two")
            ],
        }
        (root / "stations.yml").write_text(yaml.safe_dump(config))
        docker(
            "run",
            "--rm",
            "-v",
            f"{data}:/radio",
            "--entrypoint",
            "ffmpeg",
            "yogurt-radio",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=10",
            "-ar",
            "48000",
            "-ac",
            "2",
            "/radio/one/fallback/seed.flac",
        )
        seed = data / "one/fallback/seed.flac"
        shutil.copyfile(seed, data / "two/fallback/seed.flac")
        shutil.copyfile(seed, data / "one/ready/001.flac")
        shutil.copyfile(seed, data / "one/playing/002.flac")
        (data / "two/ready/001-bad.flac").write_bytes(b"invalid")
        shutil.copyfile(seed, data / "two/ready/002.flac")
        env = [
            "-e",
            "ICECAST_SOURCE_PASSWORD=fixture-source-password",
            "-e",
            "ICECAST_ADMIN_PASSWORD=fixture-admin-password",
        ]
        try:
            docker(
                "run",
                "-d",
                "--name",
                name,
                "-p",
                "127.0.0.1::80",
                *env,
                "-v",
                f"{data}:/radio",
                "-v",
                f"{root / 'stations.yml'}:/app/stations.yml:ro",
                "yogurt-radio",
            )
            port = json.loads(docker("inspect", name))[0]["NetworkSettings"]["Ports"][
                "80/tcp"
            ][0]["HostPort"]
            base = f"http://127.0.0.1:{port}"

            def healthy():
                try:
                    with urllib.request.urlopen(
                        base + "/healthz", timeout=2
                    ) as response:
                        return response.status == 200
                except (OSError, urllib.error.URLError):
                    return False

            wait_for(healthy)
            for path in (
                "/admin/stats",
                "/status-json.xsl",
                "/next/one",
                "/streams/unknown.mp3",
            ):
                try:
                    urllib.request.urlopen(base + path, timeout=2)
                except urllib.error.HTTPError as error:
                    assert error.code == 404
                else:
                    raise AssertionError("unexpected public route")

            for station in ("one", "two"):
                with urllib.request.urlopen(
                    base + f"/streams/{station}.mp3", timeout=5
                ) as stream:
                    assert stream.headers.get_content_type() == "audio/mpeg"
                    assert len(stream.read(8192)) == 8192

            def drained():
                return not any(data.glob("*/ready/*.flac")) and not any(
                    data.glob("*/playing/*.flac")
                )

            # a single connection survives fresh audio draining and fallback playback
            with urllib.request.urlopen(base + "/streams/one.mp3", timeout=5) as stream:
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    assert stream.read(8192)
                wait_for(drained)
                assert all(
                    (data / station / "fallback/seed.flac").exists()
                    for station in ("one", "two")
                )
                shutil.copyfile(seed, data / "one/ready/003.flac")
                wait_for(lambda: not (data / "one/ready/003.flac").exists())
                assert stream.read(8192)

            for service in ("liquidsoap", "icecast", "api"):
                service_path = f"/run/service/{service}"

                def pid():
                    return docker(
                        "exec", name, "/command/s6-svstat", "-o", "pid", service_path
                    )

                before = pid()
                docker("exec", name, "/command/s6-svc", "-k", service_path)
                wait_for(lambda: pid() not in (before, "-1"))
                wait_for(healthy)
            docker("restart", name)
            port = json.loads(docker("inspect", name))[0]["NetworkSettings"]["Ports"][
                "80/tcp"
            ][0]["HostPort"]
            base = f"http://127.0.0.1:{port}"
            wait_for(healthy)
            with urllib.request.urlopen(base + "/streams/two.mp3", timeout=5) as stream:
                sample = stream.read(48000)
                assert sample
            (root / "sample.mp3").write_bytes(sample)
            decoded = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{root}:/fixture:ro",
                    "--entrypoint",
                    "ffmpeg",
                    "yogurt-radio",
                    "-v",
                    "error",
                    "-i",
                    "/fixture/sample.mp3",
                    "-f",
                    "s16le",
                    "-ac",
                    "1",
                    "-",
                ],
                check=True,
                capture_output=True,
            ).stdout
            samples = array.array("h", decoded)
            assert samples and max(abs(value) for value in samples) > 100, (
                "stream is silent"
            )
            print("radio integration passed")
        except Exception:
            with contextlib.suppress(Exception):
                subprocess.run(["docker", "logs", "--tail", "100", name], check=False)
            raise
        finally:
            with contextlib.suppress(subprocess.CalledProcessError):
                docker("rm", "-f", name)


if __name__ == "__main__":
    main()
