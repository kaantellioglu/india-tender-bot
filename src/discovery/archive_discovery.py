"""Source URL discovery for market-intelligence extraction.

This layer decides which public tender/result/archive pages should be inspected for
historical and active market intelligence. It never handles procurement transactions or protected portal interactions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin
import logging

import yaml

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
PORTAL_RULES_PATH = ROOT / "config" / "portal_rules.yaml"


@dataclass(frozen=True)
class SourceCandidate:
    url: str
    source_kind: str = "tender"
    reason: str = "configured"


def load_portal_rules() -> dict:
    if not PORTAL_RULES_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(PORTAL_RULES_PATH.read_text(encoding="utf-8")) or {}
        return data.get("portals", data) or {}
    except Exception as exc:
        logger.warning("portal_rules.yaml okunamadi: %s", exc)
        return {}


def _add_unique(rows: list[SourceCandidate], seen: set[str], url: str | None, source_kind: str, reason: str) -> None:
    if not url:
        return
    url = str(url).strip()
    if not url or url in seen:
        return
    seen.add(url)
    rows.append(SourceCandidate(url=url, source_kind=source_kind, reason=reason))


def discover_sources(portal: dict, rules: dict | None = None) -> list[SourceCandidate]:
    """Return public source URLs for one portal.

    Priority:
    1. explicit ``source_urls`` from config/portal_rules.yaml
    2. existing ``tender_search_url``
    3. existing ``award_url`` when different from the tender URL
    4. conservative configured archive/result paths only when enabled in rules
    """
    rules = rules if rules is not None else load_portal_rules().get(portal.get("id", ""), {})
    rows: list[SourceCandidate] = []
    seen: set[str] = set()

    for item in rules.get("source_urls", []) or []:
        if isinstance(item, str):
            _add_unique(rows, seen, item, "configured", "portal_rules.source_urls")
        elif isinstance(item, dict):
            _add_unique(rows, seen, item.get("url"), item.get("kind", "configured"), item.get("reason", "portal_rules.source_urls"))

    _add_unique(rows, seen, portal.get("tender_search_url"), "tender", "portal_master.tender_search_url")
    award_url = portal.get("award_url")
    if award_url and award_url != portal.get("tender_search_url"):
        _add_unique(rows, seen, award_url, "award_or_archive", "portal_master.award_url")

    # Only use generated candidates when a portal-specific rule explicitly asks for it.
    # This prevents the bot from hammering broken URLs on every portal.
    if rules.get("discover_common_archive_paths"):
        base = portal.get("website")
        for path in rules.get("common_archive_paths", ["/tenders", "/tender", "/active-tenders", "/archive-tenders", "/awards", "/award", "/procurement"]):
            if base:
                _add_unique(rows, seen, urljoin(base.rstrip("/") + "/", path.lstrip("/")), "archive_guess", "common_archive_path")

    return rows
