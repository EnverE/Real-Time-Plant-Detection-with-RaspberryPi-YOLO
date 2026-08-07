"""
Central configuration for the laptop side of the system.

Settings are resolved in this order (later wins):

    1. the defaults in DEFAULTS below
    2. config.json in the repository root (create it from config.example.json)
    3. environment variables (PLANT_PI_HOST, PLANT_PI_PASSWORD, ...)

config.json is git-ignored, so machine-specific values and the Pi password
never end up in the repository.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"

DEFAULTS = {
    "laptop": {
        "listen_host": "0.0.0.0",
        "listen_port": 8080,
        # Address the Pi should stream to (the laptop's address on the hotspot).
        # Windows Internet Connection Sharing always uses 192.168.137.1.
        "hotspot_ip": "192.168.137.1",
    },
    "model": {
        "path": "models/best5.pt",
        "confidence": 0.7,
        "weed_class": "other",
        "device": "auto",          # "auto" | "cpu" | 0 | 1 | ...
        "tracker": "bytetrack.yaml",
    },
    "pump": {
        "mode": "auto",            # "auto" | "manual"
        "duration_s": 2.0,
        "min_detections": 1,
        "litres_per_activation": 0.05,
    },
    "pi": {
        "host": "192.168.137.100",
        "port": 22,
        "user": "pi",
        "password": "",
        "key_file": "",
        "remote_dir": "/home/pi/plant-detection",
        # false = don't SSH anywhere, just wait for a sender to connect
        "auto_start": True,
    },
    "camera": {
        "width": 640,
        "height": 480,
        "fps": 30,
        "jpeg_quality": 80,
    },
    "logging": {
        "csv_dir": "logs",
    },
}

# environment variable -> (section, key, type)
ENV_MAP = {
    "PLANT_LISTEN_PORT": ("laptop", "listen_port", int),
    "PLANT_MODEL_PATH": ("model", "path", str),
    "PLANT_MODEL_DEVICE": ("model", "device", str),
    "PLANT_PI_HOST": ("pi", "host", str),
    "PLANT_PI_PORT": ("pi", "port", int),
    "PLANT_PI_USER": ("pi", "user", str),
    "PLANT_PI_PASSWORD": ("pi", "password", str),
    "PLANT_PI_KEY_FILE": ("pi", "key_file", str),
    "PLANT_PI_REMOTE_DIR": ("pi", "remote_dir", str),
}


def _merge(base, override):
    """Recursively merge `override` into a copy of `base`."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path=None):
    """Return the merged configuration dictionary."""
    path = Path(path) if path else CONFIG_PATH

    file_cfg = {}
    if path.exists():
        try:
            file_cfg = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path.name} is not valid JSON: {exc}") from exc

    cfg = _merge(DEFAULTS, file_cfg)

    for env_name, (section, key, cast) in ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw:
            cfg[section][key] = cast(raw)

    return cfg


def resolve_path(value):
    """Turn a config path into an absolute path, relative to the repo root."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (ROOT / p)


def device_for(setting):
    """Map the `model.device` setting onto an argument Ultralytics accepts."""
    if setting != "auto":
        return setting
    try:
        import torch
        if torch.cuda.is_available():
            return 0
    except ImportError:
        pass
    return "cpu"
