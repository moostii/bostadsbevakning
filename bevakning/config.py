from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml


@dataclass
class Config:
    areas: list[str] = field(default_factory=list)
    exclude_areas: list[str] = field(default_factory=list)
    min_rooms: float | None = None
    max_rooms: float | None = None
    min_size_m2: float | None = None
    max_rent_sek: int | None = None
    keywords_any: list[str] = field(default_factory=list)
    keywords_exclude: list[str] = field(default_factory=list)


_LIST_KEYS = {"areas", "exclude_areas", "keywords_any", "keywords_exclude"}


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: förväntade nyckel/värde-par på toppnivå")
    known = {f.name for f in fields(Config)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(
            f"{path}: okänd(a) nyckel/nycklar: {', '.join(unknown)}. "
            f"Giltiga: {', '.join(sorted(known))}"
        )
    kwargs = {}
    for key, value in raw.items():
        if key in _LIST_KEYS:
            if value is None:
                value = []
            if not isinstance(value, list):
                raise ValueError(f"{path}: {key} måste vara en lista")
            value = [str(v) for v in value]
        elif value is not None and not isinstance(value, (int, float)):
            raise ValueError(f"{path}: {key} måste vara ett tal eller null")
        kwargs[key] = value
    return Config(**kwargs)
