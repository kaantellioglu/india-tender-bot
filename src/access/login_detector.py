"""Detect portal access and registration requirements for market-intelligence extraction.

This module deliberately does NOT support or plan bid/offer submission automation.
Its only goal is to identify whether the bot can collect tender/award intelligence
from public pages, browser-rendered pages, or credential-protected document areas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class LoginSignal:
    # Kept as LoginSignal for backwards-compatible imports, but it now means
    # "portal access signal", not bid/offer automation.
    access_type: str = "public"  # public / credentials_required / vendor_registration_required / protected_manual_review / document_access_review
    required_items: list[str] = field(default_factory=list)
    data_access: str = "public"  # public / browser / credentials / registration / manual_review
    automation_possible: str = "data_extraction_only"  # data_extraction_only / partial_with_credentials / manual_review_only
    action: str = "Public market-intelligence extraction can continue"
    confidence: str = "Low"
    signals: list[str] = field(default_factory=list)
    excluded_scope: str = "No bid/offer submission automation"


SIGNAL_PATTERNS = [
    ("captcha", re.compile(r"captcha|i am not a robot|recaptcha", re.I), "CAPTCHA / human verification"),
    ("dsc", re.compile(r"digital signature|\bDSC\b|class\s*3 certificate|signing certificate", re.I), "digital signature / certificate"),
    ("credential", re.compile(r"vendor login|supplier login|login|sign\s*in|user\s*name|username|password", re.I), "username/password"),
    ("registration", re.compile(r"vendor registration|supplier registration|register as vendor|empanelment", re.I), "vendor registration / empanelment"),
    # These are useful signals for portal/document access, but they are NOT used
    # to create a bidding workflow. We keep them as commercial access indicators.
    ("commercial_access", re.compile(r"tender fee|emd|earnest money|bid security", re.I), "commercial access terms found"),
]


def detect_login_requirements(text: str, url: str = "") -> LoginSignal:
    """Return access requirement signals for data extraction.

    Scope note:
    - The bot may collect public tender/award/price intelligence.
    - It may flag that credentials/registration are needed to access documents.
    - It must not automate offer submission, DSC signing, CAPTCHA bypass, EMD payment,
      or any bid/proposal transaction.
    """
    hay = f"{text or ''}\n{url or ''}"
    signal = LoginSignal()
    for key, pattern, item in SIGNAL_PATTERNS:
        if pattern.search(hay):
            signal.signals.append(key)
            if item not in signal.required_items:
                signal.required_items.append(item)

    if not signal.signals:
        return signal

    if "captcha" in signal.signals or "dsc" in signal.signals:
        signal.access_type = "protected_manual_review"
        signal.data_access = "manual_review"
        signal.automation_possible = "manual_review_only"
        signal.action = "Protected portal element found. Use only public intelligence extraction; protected access requires human review."
        signal.confidence = "High"
    elif "credential" in signal.signals:
        signal.access_type = "credentials_required"
        signal.data_access = "credentials"
        signal.automation_possible = "partial_with_credentials"
        signal.action = "Credentials may be needed for private documents. Continue public data extraction; review credential availability outside GitHub."
        signal.confidence = "High"
    elif "registration" in signal.signals:
        signal.access_type = "vendor_registration_required"
        signal.data_access = "registration"
        signal.automation_possible = "partial_with_registration"
        signal.action = "Vendor registration/empanelment may be needed for private documents. Public intelligence extraction continues."
        signal.confidence = "Medium"
    elif "commercial_access" in signal.signals:
        signal.access_type = "document_access_review"
        signal.data_access = "public_or_document_restricted"
        signal.automation_possible = "data_extraction_only"
        signal.action = "Commercial access terms detected. Capture intelligence only; do not create bid/payment workflow."
        signal.confidence = "Medium"
    else:
        signal.access_type = "access_review"
        signal.data_access = "manual_review"
        signal.automation_possible = "manual_review_only"
        signal.action = "Manual source-access review may be required for intelligence extraction."
        signal.confidence = "Medium"
    return signal
