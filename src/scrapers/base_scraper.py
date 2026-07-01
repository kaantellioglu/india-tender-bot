"""Base classes for tender scrapers."""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from ..access.content_classifier import classify_exception, classify_bytes
from ..access.login_detector import detect_login_requirements
from ..diagnostics.source_failure import DiagnosticRecorder

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.7",
    "Connection": "keep-alive",
}


@dataclass
class TenderLead:
    """One tender/notice candidate found in a portal."""

    portal_id: str
    portal_name: str
    title: str
    url: str
    matched_keyword: Optional[str] = None
    published_date: Optional[str] = None
    file_type: Optional[str] = None  # pdf/html/doc/xls
    raw_snippet: Optional[str] = None
    extra: dict = field(default_factory=dict)


class BaseScraper:
    """Common scraper interface and request diagnostics."""

    def __init__(
        self,
        portal: dict,
        keywords: List[dict],
        timeout: int = 20,
        request_delay: float = 1.2,
        diagnostics: DiagnosticRecorder | None = None,
    ):
        self.portal = portal
        self.keywords = [k["keyword"] if isinstance(k, dict) else str(k) for k in keywords]
        self.timeout = timeout
        self.request_delay = request_delay
        self.diagnostics = diagnostics
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_leads(self) -> List[TenderLead]:
        raise NotImplementedError

    def _record_action_from_html(self, url: str, html: str) -> None:
        if not self.diagnostics:
            return
        signal = detect_login_requirements(html, url)
        if signal.access_type != "public":
            self.diagnostics.record_action(
                portal=self.portal,
                url=url,
                action_type=signal.access_type,
                required_items=signal.required_items,
                data_access=signal.data_access,
                automation_possible=signal.automation_possible,
                next_action=signal.action,
                confidence=signal.confidence,
                signals=signal.signals,
            )

    def _get(self, url: str) -> Optional[requests.Response]:
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            time.sleep(self.request_delay)
            content_type = resp.headers.get("Content-Type", "")
            preview = ""
            try:
                if "text" in content_type.lower() or "html" in content_type.lower():
                    preview = resp.text[:3000]
            except Exception:
                preview = ""

            c = classify_bytes(
                url=url,
                data=resp.content[:4096] if resp.content else b"",
                content_type=content_type,
                http_status=resp.status_code,
                final_url=resp.url,
                text_preview=preview,
            )

            if resp.status_code == 200:
                if c.looks_like_login:
                    self._record_action_from_html(url, preview)
                return resp

            logger.warning("HTTP %s -> %s", resp.status_code, url)
            if self.diagnostics:
                action_required = "manual_review"
                retry_strategy = "review_portal_url"
                if resp.status_code in (401, 403):
                    action_required = "access_review_required"
                    retry_strategy = "browser_fetch_or_credential_review"
                    self._record_action_from_html(url, preview)
                elif resp.status_code == 404:
                    action_required = "portal_url_fix_required"
                    retry_strategy = "update_portal_url"
                elif 300 <= resp.status_code < 400:
                    action_required = "redirect_review"
                    retry_strategy = "follow_final_url"
                self.diagnostics.record_failure(
                    portal=self.portal,
                    url=url,
                    failure_type=c.failure_type or f"http_{resp.status_code}",
                    http_status=resp.status_code,
                    content_type=content_type,
                    final_url=resp.url,
                    action_required=action_required,
                    retry_strategy=retry_strategy,
                    signals=c.signals,
                )
        except requests.RequestException as exc:
            failure_type, signals = classify_exception(exc)
            logger.warning("Istek basarisiz: %s (%s)", url, exc)
            if self.diagnostics:
                strategy = {
                    "ssl_error": "browser_fetch_or_ssl_fallback",
                    "dns_error": "update_portal_domain",
                    "timeout": "retry_or_reduce_timeout",
                    "redirect_loop": "inspect_redirect_chain",
                    "connection_refused": "retry_later_or_alternative_source",
                }.get(failure_type, "manual_review")
                self.diagnostics.record_failure(
                    portal=self.portal,
                    url=url,
                    failure_type=failure_type,
                    action_required="source_access_review",
                    retry_strategy=strategy,
                    signals=signals,
                    note=str(exc)[:500],
                )
        return None

    def _matches_keyword(self, text: str) -> Optional[str]:
        text_low = (text or "").lower()
        for kw in self.keywords:
            if kw.lower() in text_low:
                return kw
        return None
