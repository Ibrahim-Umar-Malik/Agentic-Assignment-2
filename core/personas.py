"""Persona profile defaults (no heavy imports, safe to load before the eval environment is set up)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def persona_floor(persona: str | None) -> float:
    """Default hourly floor: the persona profile's value, calibrated on real contract rates (docs/DATA_CARD.md)."""
    try:
        prof = json.loads((ROOT / "data" / "personas" / (persona or "ai_ml") / "profile.json").read_text())
        return float(prof.get("hourly_floor_usd") or 30)
    except (OSError, ValueError):
        return 30.0
