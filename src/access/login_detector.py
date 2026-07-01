"""Detect source-access signals for market-intelligence extraction.

This module is intentionally limited to read-only market intelligence:
- discover public tender/result/archive data
- identify whether a document/listing source is public, browser-rendered, or protected
- report source-access issues for human review

It does not support and must not imply procurement transaction automation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EXCLUDED_SCOPE = "no_procurement_transaction_automation"


@dataclass
class LoginSignal:
    # Kept as LoginSignal for backwards-compatible imports, but it means
    # "source access signal", not login workflow.
    access_type: str = "public"  # public / credential_document_area / registration_document_area / protected_source_review / access_review
    required_items: list[str] = field(default_factory=list)
    data_access: str = "public"  # public / browser / credential_document_area / registration_document_area / protected_source_review
    automation_possible: str = "public_data_extraction_only"
    action: str = "Continue public market-intelligence extraction"
    confidence: str = "Low"
    signals: list[str] = field(default_factory=list)
    excluded_scope: str = EXCLUDED_SCOPE


# Transaction-related words are intentionally not used as requirements. They may
# appear inside tender pages, but this bot never creates a procurement transaction flow.
SIGNAL_PATTERNS = [
    ("protected_source", re.compile(r"captcha|i am not a robot|recaptcha|digital signature|\bDSC\b|class\s*3 certificate|signing certificate", re.I), "protected source / human verification"),
    ("credential_area", re.compile(r"vendor login|supplier login|document login|login to download|sign\s*in|user\s*name|username|password", re.I), "read-only credential check"),
    ("registration_area", re.compile(r"vendor registration|supplier registration|register as vendor|empanelment", re.I), "vendor registration status check"),
    ("browser_rendered", re.compile(r"enable javascript|javascript is required|app-root|ng-version|react|__next", re.I), "browser-rendered public page"),
]


def detect_login_requirements(text: str, url: str = "") -> LoginSignal:
    """Return source-access requirement signals for intelligence extraction only."""
    hay = f"{text or ''}\n{url or ''}"
    signal = LoginSignal()
    for key, pattern, item in SIGNAL_PATTERNS:
        if pattern.search(hay):
            signal.signals.append(key)
            if item not in signal.required_items:
                signal.required_items.append(item)

    if not signal.signals:
        return signal

    if "protected_source" in signal.signals:
        signal.access_type = "protected_source_review"
        signal.data_access = "protected_source_review"
        signal.automation_possible = "manual_source_review_only"
        signal.action = "Protected source element detected. Use public pages/archives only; do not automate protected interactions."
        signal.confidence = "High"
    elif "credential_area" in signal.signals:
        signal.access_type = "credential_document_area"
        signal.data_access = "credential_document_area"
        signal.automation_possible = "public_data_plus_optional_readonly_credentials"
        signal.action = "Credentials may be needed only to view/download documents. Continue public extraction and verify read-only access outside the repository."
        signal.confidence = "High"
    elif "registration_area" in signal.signals:
        signal.access_type = "registration_document_area"
        signal.data_access = "registration_document_area"
        signal.automation_possible = "public_data_plus_registration_status_check"
        signal.action = "Registration may affect document visibility. Public intelligence extraction continues."
        signal.confidence = "Medium"
    elif "browser_rendered" in signal.signals:
        signal.access_type = "browser_scrape_needed"
        signal.data_access = "browser"
        signal.automation_possible = "browser_public_data_extraction"
        signal.action = "Build browser-rendered public data scraper for tender/result tables."
        signal.confidence = "Medium"
    else:
        signal.access_type = "access_review"
        signal.data_access = "source_review"
        signal.automation_possible = "source_review_only"
        signal.action = "Review source access for market-intelligence extraction."
        signal.confidence = "Medium"
    return signal
