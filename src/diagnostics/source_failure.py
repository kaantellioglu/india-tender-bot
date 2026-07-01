"""Persistent diagnostic queues for source failures and manual actions.

These files are committed by GitHub Actions and then exported into docs/data.json
so the dashboard shows *why* a source failed and what action is needed.
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


@dataclass
class PortalAction:
    timestamp: str
    portal: str
    portal_id: str
    url: str
    action_type: str
    required_items: list[str] = field(default_factory=list)
    automation_possible: str = "partial"
    next_action: str = "Manual review required"
    confidence: str = "Medium"
    status: str = "open"
    signals: list[str] = field(default_factory=list)
    count: int = 1
    last_seen: str = ""


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
        automation_possible: str = "partial",
        next_action: str = "Manual review required",
        confidence: str = "Medium",
        signals: Optional[list[str]] = None,
    ) -> None:
        ts = now_utc()
        rows = _load_json_list(self.actions_path)
        key = (portal.get("id", ""), url, action_type)
        for row in rows:
            if (row.get("portal_id"), row.get("url"), row.get("action_type")) == key:
                row["count"] = int(row.get("count", 1)) + 1
                row["last_seen"] = ts
                row["required_items"] = sorted(set((row.get("required_items") or []) + (required_items or [])))
                row["automation_possible"] = automation_possible
                row["next_action"] = next_action
                row["confidence"] = confidence
                row["signals"] = sorted(set((row.get("signals") or []) + (signals or [])))
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
            automation_possible=automation_possible,
            next_action=next_action,
            confidence=confidence,
            signals=signals or [],
        )
        rows.append(asdict(action))
        _save_json_list(self.actions_path, rows[-1000:])
