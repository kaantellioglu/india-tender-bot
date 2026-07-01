"""Persistent diagnostic queues for source failures and access review.

The queue is for market-intelligence extraction only:
- public tender/award/result data collection
- document availability checks
- portal URL/access health

It explicitly excludes bid/offer submission, DSC signing, CAPTCHA bypass, payments,
EMD handling, and any transaction on procurement portals.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DEFAULT_FAILURES = DATA_DIR / "source_failures.json"
DEFAULT_ACTIONS = DATA_DIR / "action_queue.json"
MARKET_INTELLIGENCE_SCOPE = "market_intelligence_only"
EXCLUDED_SCOPE = "no_bid_or_offer_submission_automation"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@dataclass
class SourceFailure:
    timestamp: str
    portal: str
    portal_id: str
    url: str
    failure_type: str
    http_status: Optional[int] = None
    content_type: str = ""
    final_url: str = ""
    action_required: str = "review"
    retry_strategy: str = "manual_review"
    signals: list[str] = field(default_factory=list)
    note: str = ""
    count: int = 1
    last_seen: str = ""
    scope: str = MARKET_INTELLIGENCE_SCOPE
    excluded_scope: str = EXCLUDED_SCOPE


@dataclass
class PortalAction:
    timestamp: str
    portal: str
    portal_id: str
    url: str
    action_type: str
    required_items: list[str] = field(default_factory=list)
    data_access: str = "public"
    automation_possible: str = "data_extraction_only"
    next_action: str = "Review source access for intelligence extraction"
    next_technical_action: str = "Continue public scraping or create parser rule"
    next_business_action: str = "Check whether public documents/award data are available"
    confidence: str = "Medium"
    status: str = "open"
    signals: list[str] = field(default_factory=list)
    count: int = 1
    last_seen: str = ""
    scope: str = MARKET_INTELLIGENCE_SCOPE
    excluded_scope: str = EXCLUDED_SCOPE


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_json_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_technical_action(action_type: str, data_access: str) -> str:
    if action_type in {"credentials_required", "vendor_registration_required"}:
        return "Keep public scraping active; only use credentials for document discovery after approved setup"
    if action_type == "protected_manual_review":
        return "Do not automate protected steps; use public pages and result archives only"
    if action_type == "document_access_review":
        return "Check whether documents are publicly downloadable or mirrored in award/archive pages"
    if data_access == "browser":
        return "Build browser-rendered data scraper for public tender/result tables"
    return "Continue public tender/award/result extraction"


def _default_business_action(action_type: str) -> str:
    if action_type == "credentials_required":
        return "Confirm if ESKA has read-only vendor credentials for document access; never store secrets in repository"
    if action_type == "vendor_registration_required":
        return "Check vendor registration/empanelment status for document visibility only"
    if action_type == "protected_manual_review":
        return "Human review only for protected pages; no CAPTCHA/DSC/payment/offer automation"
    if action_type == "document_access_review":
        return "Review commercial terms only as intelligence; no transaction workflow"
    return "No business transaction required"


class DiagnosticRecorder:
    def __init__(self, failures_path: Path = DEFAULT_FAILURES, actions_path: Path = DEFAULT_ACTIONS):
        self.failures_path = failures_path
        self.actions_path = actions_path

    def record_failure(
        self,
        portal: dict,
        url: str,
        failure_type: str,
        http_status: Optional[int] = None,
        content_type: str = "",
        final_url: str = "",
        action_required: str = "review",
        retry_strategy: str = "manual_review",
        signals: Optional[list[str]] = None,
        note: str = "",
    ) -> None:
        ts = now_utc()
        rows = _load_json_list(self.failures_path)
        key = (portal.get("id", ""), url, failure_type)
        for row in rows:
            if (row.get("portal_id"), row.get("url"), row.get("failure_type")) == key:
                row["count"] = int(row.get("count", 1)) + 1
                row["last_seen"] = ts
                row["http_status"] = http_status
                row["content_type"] = content_type or row.get("content_type", "")
                row["final_url"] = final_url or row.get("final_url", "")
                row["action_required"] = action_required
                row["retry_strategy"] = retry_strategy
                row["signals"] = sorted(set((row.get("signals") or []) + (signals or [])))
                row["note"] = note or row.get("note", "")
                row["scope"] = MARKET_INTELLIGENCE_SCOPE
                row["excluded_scope"] = EXCLUDED_SCOPE
                _save_json_list(self.failures_path, rows[-1000:])
                return
        failure = SourceFailure(
            timestamp=ts,
            last_seen=ts,
            portal=portal.get("name", ""),
            portal_id=portal.get("id", ""),
            url=url,
            failure_type=failure_type,
            http_status=http_status,
            content_type=content_type,
            final_url=final_url or url,
            action_required=action_required,
            retry_strategy=retry_strategy,
            signals=signals or [],
            note=note,
        )
        rows.append(asdict(failure))
        _save_json_list(self.failures_path, rows[-1000:])

    def record_action(
        self,
        portal: dict,
        url: str,
        action_type: str,
        required_items: Optional[list[str]] = None,
        automation_possible: str = "data_extraction_only",
        next_action: str = "Review source access for intelligence extraction",
        confidence: str = "Medium",
        signals: Optional[list[str]] = None,
        data_access: str = "public",
        next_technical_action: Optional[str] = None,
        next_business_action: Optional[str] = None,
    ) -> None:
        ts = now_utc()
        rows = _load_json_list(self.actions_path)
        key = (portal.get("id", ""), url, action_type)
        tech = next_technical_action or _default_technical_action(action_type, data_access)
        biz = next_business_action or _default_business_action(action_type)
        for row in rows:
            if (row.get("portal_id"), row.get("url"), row.get("action_type")) == key:
                row["count"] = int(row.get("count", 1)) + 1
                row["last_seen"] = ts
                row["required_items"] = sorted(set((row.get("required_items") or []) + (required_items or [])))
                row["data_access"] = data_access
                row["automation_possible"] = automation_possible
                row["next_action"] = next_action
                row["next_technical_action"] = tech
                row["next_business_action"] = biz
                row["confidence"] = confidence
                row["signals"] = sorted(set((row.get("signals") or []) + (signals or [])))
                row["scope"] = MARKET_INTELLIGENCE_SCOPE
                row["excluded_scope"] = EXCLUDED_SCOPE
                _save_json_list(self.actions_path, rows[-1000:])
                return
        action = PortalAction(
            timestamp=ts,
            last_seen=ts,
            portal=portal.get("name", ""),
            portal_id=portal.get("id", ""),
            url=url,
            action_type=action_type,
            required_items=required_items or [],
            data_access=data_access,
            automation_possible=automation_possible,
            next_action=next_action,
            next_technical_action=tech,
            next_business_action=biz,
            confidence=confidence,
            signals=signals or [],
        )
        rows.append(asdict(action))
        _save_json_list(self.actions_path, rows[-1000:])
