"""Persistent user settings and user-defined sites (JSON in the platform config dir)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

APP = "artairmass"

DEFAULTS: dict = {
    "site": "lco",
    "airmass_model": "hardie",
    "airmass_limit": 2.0,
    "twilight": "astronomical",     # dark time definition: nautical | astronomical
    "refraction": False,
    "theme": "dark",                # light | dark | red
    "timestep": "1 h",
    "sleep_s": 5,
    "plot_step_min": 2,
    "semester_a": [2, 7],           # Feb–Jul
    "moon_max_illum": 1.0,
    "moon_min_sep": 0.0,
    "last_list": "",
    "ui_scale": 1.0,
}


def config_dir() -> Path:
    return Path(os.environ.get("ARTAIRMASS_CONFIG_DIR") or user_config_dir(APP))


def cache_dir() -> Path:
    return Path(os.environ.get("ARTAIRMASS_CACHE_DIR") or user_cache_dir(APP))


def _read(name: str, default):
    path = config_dir() / name
    try:
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        # Corrupt file: keep a copy for the user and fall back to defaults.
        try:
            path.replace(path.with_suffix(".corrupt.json"))
        except OSError:
            pass
        return default


def _write(name: str, data) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, d / name)  # atomic


def load_settings() -> dict:
    stored = _read("settings.json", {})
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def save_settings(updates: dict) -> dict:
    s = load_settings()
    s.update({k: v for k, v in updates.items() if k in DEFAULTS})
    _write("settings.json", s)
    return s


def load_user_sites() -> list[dict]:
    return _read("sites.json", [])


def save_user_sites(sites: list[dict]) -> None:
    _write("sites.json", sites)
