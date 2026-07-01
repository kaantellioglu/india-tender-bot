"""config/*.yaml dosyalarini okuyan basit yardimci fonksiyonlar."""
from __future__ import annotations

from pathlib import Path
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_portals(only_enabled: bool = True, tiers: list[str] | None = None) -> list[dict]:
    with open(CONFIG_DIR / "portals.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    portals = data.get("portals", [])
    if only_enabled:
        portals = [p for p in portals if p.get("enabled", True)]
    if tiers:
        portals = [p for p in portals if p.get("tier") in tiers]
    return portals


def load_keywords() -> list[dict]:
    with open(CONFIG_DIR / "keywords.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("keywords", [])


def load_competitors() -> list[dict]:
    with open(CONFIG_DIR / "competitors.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("competitors", [])
