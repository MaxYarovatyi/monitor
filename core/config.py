import json
from pathlib import Path
import sys

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "broadcast_config.json"

DEFAULT_THRESHOLDS = {
    "min_kbps":100,
    "warn_kbps": 500,
    "cc_warn_per_min": 1,
    "cc_alarm_per_min": 10,
    "silence_db": -50.0,
    "silence_s": 5.0,
    "hysteresis_pct": 10,
    "raise_after_s": 3,
    "black_s": 5.0,
    "black_level": 16.0,
    "black_std": 6.0,
    "freeze_s": 10.0,
    "freeze_diff": 0.5
}

def load_config(path=CONFIG_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], {}
    if isinstance(data, list):
        return data, {}
    return data.get("streams", []), data.get("defaults", {})

def save_config(streams, defaults, path=CONFIG_FILE):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"streams": streams, "defaults": defaults}, f, ensure_ascii=False, indent=2)
    tmp.replace(path)