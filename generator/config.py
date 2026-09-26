import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    prompt: str


@dataclass(frozen=True)
class Config:
    stations: tuple[Station, ...]
    segment_seconds: int
    crossfade_seconds: int
    buffer_low_seconds: int
    buffer_target_seconds: int


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    fields = set(Config.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) != fields:
        raise ValueError("invalid configuration fields")
    for key in fields - {"stations"}:
        if type(raw[key]) is not int:
            raise ValueError(f"{key} must be an integer")
    if not 10 <= raw["segment_seconds"] <= 600:
        raise ValueError("segment_seconds must be between 10 and 600")
    if not 0 <= raw["crossfade_seconds"] < raw["segment_seconds"] / 2:
        raise ValueError("invalid crossfade_seconds")
    if not 0 < raw["buffer_low_seconds"] <= raw["buffer_target_seconds"] <= 86400:
        raise ValueError("invalid buffer thresholds")
    stations = []
    if not isinstance(raw["stations"], list) or not raw["stations"]:
        raise ValueError("at least one station is required")
    for item in raw["stations"]:
        if not isinstance(item, dict) or set(item) != {"id", "name", "prompt"}:
            raise ValueError("invalid station fields")
        if any(not isinstance(v, str) or not v.strip() for v in item.values()):
            raise ValueError("station fields must be nonempty strings")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item["id"]):
            raise ValueError("invalid station id")
        if item["id"] in {s.id for s in stations}:
            raise ValueError("duplicate station id")
        if any(ord(c) < 32 for c in item["name"]):
            raise ValueError("invalid station name")
        stations.append(Station(**item))
    return Config(**{**raw, "stations": tuple(stations)})
