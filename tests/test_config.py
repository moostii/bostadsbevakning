from pathlib import Path

import pytest

from bevakning.config import Config, load_config

ROOT = Path(__file__).resolve().parent.parent


def test_load_example_config():
    cfg = load_config(ROOT / "config.yaml")
    assert cfg.areas == ["Adolfsberg", "Rynninge", "Centrum"]
    assert cfg.exclude_areas == []
    assert cfg.min_rooms == 2
    assert cfg.max_rooms == 3
    assert cfg.min_size_m2 == 45
    assert cfg.max_rent_sek == 10000
    assert cfg.keywords_any == []
    assert cfg.keywords_exclude == ["korttidskontrakt", "andrahand"]


def test_unknown_key_raises(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("max_rent: 9000\n")
    with pytest.raises(ValueError, match="max_rent"):
        load_config(p)


def test_missing_keys_default(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("min_rooms: 2\n")
    cfg = load_config(p)
    assert cfg == Config(min_rooms=2)
    assert cfg.areas == [] and cfg.max_rent_sek is None


def test_empty_file_is_all_defaults(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("")
    assert load_config(p) == Config()
