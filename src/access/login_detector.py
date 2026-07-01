"""Detect login/vendor-registration/DSC/manual-action requirements."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class LoginSignal:
    access_type: str = "public"  # public/login_required/vendor_registration/dsc/captcha/manual
    required_items: list[str] = field(default_factory=list)
    automation_possible: str = "full"  # full/partial/manual_only
    action: str = "No login action required"
    confidence: str = "Low"
    signals: list[str] = field(default_factory=list)


SIGNAL_PATTERNS = [
    ("captcha", re.compile(r"captcha|i am not a robot|recaptcha", re.I), "CAPTCHA"),
    ("dsc", re.compile(r"digital signature|\bDSC\b|class\s*3 certificate|signing certificate", re.I), "DSC"),
    ("login", re.compile(r"vendor login|supplier login|bidder login|login|sign\s*in|user\s*name|username|password", re.I), "username/password"),
    ("registration", re.compile(r"vendor registration|supplier registration|register as vendor|empanelment", re.I), "vendor registration"),
    ("tender_fee", re.compile(r"tender fee|emd|earnest money|bid security", re.I), "tender fee/EMD"),
]


def detect_login_requirements(text: str, url: str = "") -> LoginSignal:
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
        signal.access_type = "manual_required"
        signal.automation_possible = "manual_only"
        signal.action = "Manual login/DSC/CAPTCHA step required before full data extraction"
        signal.confidence = "High"
    elif "login" in signal.signals:
        signal.access_type = "login_required"
        signal.automation_possible = "partial"
        signal.action = "Vendor credentials required; automate only after approved credential setup"
        signal.confidence = "High"
    elif "registration" in signal.signals:
        signal.access_type = "vendor_registration_required"
        signal.automation_possible = "partial"
        signal.action = "Vendor registration/empanelment status must be checked"
        signal.confidence = "Medium"
    else:
        signal.access_type = "manual_review"
        signal.automation_possible = "partial"
        signal.action = "Manual commercial/procurement action may be required"
        signal.confidence = "Medium"
    return signal
