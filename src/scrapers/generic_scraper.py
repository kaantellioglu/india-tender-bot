"""Generic scraper for public tender pages.

V3 upgrades:
- Reads parent table/list/card text instead of only <a> text.
- Extracts tender ref/date/closing date from row text.
- Detects access/registration/protected-page signals for intelligence extraction only.
- Calculates transparent priority score for each candidate.
- Supports portal-specific max_leads via config/portal_rules.yaml when available.
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup, Tag

from .base_scraper import BaseScraper, TenderLead
from ..access.login_detector import detect_login_requirements
from ..parsers.html_detail_parser import parse_html_text, clean_text
from ..scoring.lead_score import score_text

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PORTAL_RULES_PATH = ROOT / "config" / "portal_rules.yaml"

STRONG_DOCUMENT_HINTS = [
    "nit", "rfq", "rfp", "eoi", "corrigendum", "aoc", "loa", "foa", "boq",
    "tender no", "tender ref", "tender_no", "bid no", "e-tender", "award",
    "letter of award", "purchase order", "work order",
]
DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv")
DEFAULT_MAX_LEADS_PER_PORTAL = 120
NOISE_HINTS = [
    "contact us", "privacy", "terms", "career", "investor", "annual report", "sitemap",
    "facebook", "twitter", "linkedin", "youtube", "copyright", "about us",
]


def load_portal_rules() -> dict:
    if not PORTAL_RULES_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(PORTAL_RULES_PATH.read_text(encoding="utf-8")) or {}
        return data.get("portals", data) or {}
    except Exception as exc:
        logger.warning("portal_rules.yaml okunamadi: %s", exc)
        return {}


def parent_context_text(a: Tag) -> str:
    # Prefer table row, then list item/card-like parents, then parent text.
    for name in ["tr", "li", "article"]:
        p = a.find_parent(name)
        if p:
            return clean_text(p.get_text(" ", strip=True))
    for cls_hint in ["card", "tender", "row", "item", "notice"]:
        p = a.find_parent(class_=lambda c: c and cls_hint in str(c).lower())
        if p:
            return clean_text(p.get_text(" ", strip=True))
    return clean_text((a.parent.get_text(" ", strip=True) if a.parent else a.get_text(" ", strip=True)))


def infer_file_type(url: str) -> str:
    path = urlparse(url).path.lower().split("?")[0]
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith((".doc", ".docx")):
        return "doc"
    if path.endswith((".xls", ".xlsx", ".csv")):
        return "xls"
    return "html"


class GenericScraper(BaseScraper):
    def fetch_leads(self) -> list[TenderLead]:
        candidates: list[TenderLead] = []
        url = self.portal.get("tender_search_url") or self.portal.get("website")
        if not url:
            return candidates

        rules = load_portal_rules().get(self.portal.get("id", ""), {})
        max_leads = int(rules.get("max_leads", DEFAULT_MAX_LEADS_PER_PORTAL))
        noise_filters = [*NOISE_HINTS, *rules.get("noise_filters", [])]
        priority_keywords = [k.lower() for k in rules.get("priority_keywords", [])]

        resp = self._get(url)
        if resp is None:
            return candidates

        login_signal = detect_login_requirements(resp.text, url)
        if login_signal.access_type != "public" and self.diagnostics:
            self.diagnostics.record_action(
                portal=self.portal,
                url=url,
                action_type=login_signal.access_type,
                required_items=login_signal.required_items,
                data_access=login_signal.data_access,
                automation_possible=login_signal.automation_possible,
                next_action=login_signal.action,
                confidence=login_signal.confidence,
                signals=login_signal.signals,
            )

        soup = BeautifulSoup(resp.text, "html.parser")
        seen_urls: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            text = clean_text(a.get_text(" ", strip=True) or "")
            if not href or href.startswith("javascript:") or href.startswith("#") or href.lower().startswith("mailto:"):
                continue

            full_url = urljoin(resp.url or url, href)
            if full_url in seen_urls:
                continue

            row_text = parent_context_text(a)
            haystack = clean_text(f"{text} {href} {row_text}")
            hay_low = haystack.lower()
            if any(n in hay_low for n in noise_filters):
                continue

            file_type = infer_file_type(full_url)
            is_document = file_type in {"pdf", "doc", "xls"}
            matched_kw = self._matches_keyword(haystack)
            strong_doc_hint = is_document and any(h in hay_low for h in STRONG_DOCUMENT_HINTS)
            priority_kw_hit = any(pk in hay_low for pk in priority_keywords)

            # Accept if targeted keyword, true document hint, or row has tender reference/closing date signals.
            html_info = parse_html_text(row_text or haystack, fallback_title=text)
            tender_signal = bool(html_info.tender_ref or html_info.closing_date)
            if not (matched_kw or strong_doc_hint or priority_kw_hit or tender_signal):
                continue

            score = score_text(haystack, file_type=file_type, matched_keyword=matched_kw or "")
            if score.priority == "Low" and not strong_doc_hint and not tender_signal:
                continue

            seen_urls.add(full_url)
            title = text or html_info.title or row_text[:140] or full_url
            extra = {
                "source_type": "html_table" if row_text and row_text != text else "html_link",
                "row_text": row_text,
                "tender_ref": html_info.tender_ref,
                "tender_date": html_info.tender_date,
                "closing_date": html_info.closing_date,
                "html_confidence": html_info.confidence,
                "lead_score": score.score,
                "priority": score.priority,
                "score_reasons": score.reasons,
                "equipment_segment": score.equipment_segment,
                "equipment_type": score.equipment_type,
                "equipment_relevance": score.equipment_relevance,
            }

            candidates.append(
                TenderLead(
                    portal_id=self.portal["id"],
                    portal_name=self.portal["name"],
                    title=title[:300],
                    url=full_url,
                    matched_keyword=matched_kw,
                    published_date=html_info.tender_date,
                    file_type=file_type,
                    raw_snippet=row_text or text,
                    extra=extra,
                )
            )

        # High priority first, then higher score, then documents.
        candidates.sort(key=lambda l: (0 if l.extra.get("priority") == "High" else 1 if l.extra.get("priority") == "Medium" else 2, -(l.extra.get("lead_score") or 0), 0 if l.file_type in {"pdf", "doc", "xls"} else 1))
        leads = candidates[:max_leads]

        if len(candidates) > max_leads:
            logger.info("%s: %d aday bulundu, ilk %d tanesi alindi (limit)", self.portal["name"], len(candidates), max_leads)
        else:
            logger.info("%s: %d aday link bulundu", self.portal["name"], len(leads))
        return leads
