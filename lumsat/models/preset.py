"""Curve presets: named curves saved to disk as JSON.

Presets live in two places:

* **bundled** — ``lumsat/presets/`` shipped with the app (read-only starters).
* **user** — a per-OS application-data folder the user can write to.

A preset file is small: a name plus the curve's control points.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

from .curve import Curve

# Bundled presets ship next to the package.
BUNDLED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "presets")


def user_presets_dir() -> str:
    """Return (creating if needed) the writable per-user presets folder."""
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get(
            "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
        )
    path = os.path.join(base, "LumSat", "presets")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class Preset:
    name: str
    curve: Curve
    skin_protect: float = 0.0  # 0..1 strength of skin-tone protection

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "curve": self.curve.to_dict(),
            "skin_protect": self.skin_protect,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Preset":
        # skin_protect is optional so presets saved before it existed still load.
        return cls(
            name=data["name"],
            curve=Curve.from_dict(data["curve"]),
            skin_protect=float(data.get("skin_protect", 0.0)),
        )


def _safe_filename(name: str) -> str:
    """Turn a display name into a filesystem-safe ``.json`` filename."""
    keep = "-_ ()"
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return (cleaned or "preset") + ".json"


def save_preset(preset: Preset) -> str:
    """Write a preset to the user presets folder; return the file path."""
    path = os.path.join(user_presets_dir(), _safe_filename(preset.name))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(preset.to_dict(), fh, indent=2)
    return path


def load_presets() -> list[Preset]:
    """Load every preset from the bundled and user folders, sorted by name."""
    presets: dict[str, Preset] = {}
    for folder in (BUNDLED_DIR, user_presets_dir()):
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.lower().endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, fname), encoding="utf-8") as fh:
                    preset = Preset.from_dict(json.load(fh))
            except (OSError, ValueError, KeyError):
                continue  # skip anything malformed rather than crashing
            # User presets override bundled ones with the same name.
            presets[preset.name] = preset
    return sorted(presets.values(), key=lambda p: p.name.lower())
