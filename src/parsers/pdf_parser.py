"""Tender document parser: PDF-first with HTML fallback.

V3 goals:
- Never assume a .pdf URL is a real PDF; verify %PDF magic.
- If a PDF-looking URL returns HTML, classify it and parse the HTML fallback.
- Extract text + tables from PDFs with transparent confidence.
- Detect access/registration/protected-page signals and return them for diagnostics.
"""
from __future__ import annotations

import io
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests
import pdfplumber

from ..access.content_classifier import classify_bytes
from ..access.login_detector import detect_login_requirements
from .html_detail_parser import parse_html, parse_html_text, clean_text
from ..scoring.lead_score import score_text

logger = logging.getLogger(__name__)

TENDER_REF_PATTERNS = [
    r"(?:Tender\s*(?:No\.?|Ref\.?|ID)|Bid\s*(?:No\.?|ID)|RFQ\s*(?:No\.?)?|NIT\s*(?:No\.?)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/_.\-]{4,})",
    r"(LOA[\s_/-]?\d{4,})",
    r"(FOA[\s_/-]?\d{4,})",
    r"(AOC[\s_/-]?\d{4,})",
    r"\b([A-Z]{2,12}/[A-Z0-9_.\-/]{5,}/\d{2,4}[A-Z0-9_.\-/]*)\b",
]
DATE_PATTERNS = [
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
]
QTY_PATTERNS = [
    r"(?:Qty|Quantity|QTY)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(nos|sets?|units?|pcs|each|no\.?s?)?",
    r"\b([\d,]+)\s*(nos|sets?|units?|pcs)\s+(?:of\s+)?(?:domestic|service|pressure)?\s*(?:gas\s*)?regulators?",
]
PRICE_PATTERNS = [
    r"(?:Grand\s+Total|Total\s+Amount|Total\s+Price|Basic\s*(?:Price|Amount)|Awarded\s+Value|Contract\s+Value)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)",
    r"(?:Quoted\s+Amount|Award\s+Amount|Order\s+Value)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)",
    r"(?:Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)",
]
WINNER_PATTERNS = [
    r"(?:awarded\s+to|order\s+placed\s+on|successful\s+bidder|L1\s+bidder|contractor|supplier)\s*[:\-]?\s*(?:M/s\.?\s*)?([A-Z][A-Za-z0-9 &.,\-()]{3,80}(?:Ltd|Limited|Pvt\.?\s*Ltd\.?|LLP|Industries|Enterprises|Corporation|Company)?)",
    r"M/s\.?\s+([A-Z][A-Za-z0-9 &.,\-()]{3,80}(?:Ltd|Limited|Pvt\.?\s*Ltd\.?|LLP|Industries|Enterprises|Corporation|Company)?)",
]


@dataclass
class ExtractedTenderInfo:
    source_url: str
    tender_ref: Optional[str] = None
    tender_date: Optional[str] = None
    closing_date: Optional[str] = None
    qty: Optional[str] = None
    unit: Optional[str] = None
    total_price_inr: Optional[float] = None
    winner: Optional[str] = None
    product_description: str = ""
    equipment_segment: str = ""
    equipment_type: str = ""
    lead_score: int = 0
    priority: str = "Low"
    confidence: str = "Low"
    text_excerpt: str = ""
    source_type: str = "pdf"
    is_real_pdf: bool = False
    content_type: str = ""
    failure_type: Optional[str] = None
    detected_actions: list[dict] = field(default_factory=list)


def download_document(url: str, timeout: int = 30) -> tuple[Optional[bytes], dict]:
    meta = {"status_code": None, "content_type": "", "final_url": url}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,tr;q=0.7",
        }
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        meta = {"status_code": resp.status_code, "content_type": resp.headers.get("Content-Type", ""), "final_url": resp.url}
        if resp.status_code == 200:
            return resp.content, meta
        logger.warning("Dokuman indirilemedi (status=%s): %s", resp.status_code, url)
    except requests.RequestException as exc:
        meta["error"] = str(exc)
        logger.warning("Dokuman indirme hatasi: %s (%s)", url, exc)
    return None, meta


def extract_text_and_tables(pdf_bytes: bytes, max_pages: int = 25) -> tuple[str, list[list[list[str]]]]:
    text_chunks: list[str] = []
    tables: list[list[list[str]]] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                text_chunks.append(page.extract_text() or "")
                try:
                    for table in page.extract_tables() or []:
                        clean_table = [[clean_text(str(cell or "")) for cell in row] for row in table if row]
                        if clean_table:
                            tables.append(clean_table)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("PDF metin cikarimi basarisiz: %s", exc)
    table_text = "\n".join(" | ".join(row) for table in tables for row in table[:80])
    return "\n".join(text_chunks + [table_text]), tables


def first_match(patterns: list[str], text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return clean_text(m.group(1))
    return None


def date_near(labels: list[str], text: str) -> Optional[str]:
    low = text.lower()
    for label in labels:
        idx = low.find(label.lower())
        if idx >= 0:
            chunk = text[idx:idx + 220]
            d = first_match(DATE_PATTERNS, chunk)
            if d:
                return d
    return None


def extract_qty(text: str) -> tuple[Optional[str], Optional[str]]:
    for pat in QTY_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).replace(",", ""), (m.group(2) or "")
    return None, None


def extract_price(text: str) -> Optional[float]:
    raw = first_match(PRICE_PATTERNS, text)
    if not raw:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def parse_textual_content(info: ExtractedTenderInfo, text: str) -> ExtractedTenderInfo:
    compact = clean_text(text)
    info.text_excerpt = compact[:1000]
    info.tender_ref = first_match(TENDER_REF_PATTERNS, compact)
    info.tender_date = date_near(["tender date", "date of tender", "start date", "published", "issue date"], compact) or first_match(DATE_PATTERNS, compact)
    info.closing_date = date_near(["closing date", "due date", "last date", "end date", "submission deadline", "document download end date"], compact)
    info.qty, info.unit = extract_qty(compact)
    info.total_price_inr = extract_price(compact)
    info.winner = first_match(WINNER_PATTERNS, compact)
    info.product_description = compact[:600]
    score = score_text(compact, file_type=info.source_type, matched_keyword="")
    info.lead_score = score.score
    info.priority = score.priority
    info.equipment_segment = score.equipment_segment
    info.equipment_type = score.equipment_type
    filled = sum(bool(x) for x in [info.tender_ref, info.tender_date, info.closing_date, info.qty, info.total_price_inr, info.winner])
    info.confidence = "High" if filled >= 4 else "Medium" if filled >= 2 else "Low"
    return info


def parse_tender_pdf(url: str) -> ExtractedTenderInfo:
    info = ExtractedTenderInfo(source_url=url)
    data, meta = download_document(url)
    info.content_type = meta.get("content_type", "") or ""

    if not data:
        info.failure_type = "download_failed"
        return info

    text_preview = ""
    try:
        text_preview = data[:8000].decode("utf-8", errors="ignore")
    except Exception:
        pass

    classification = classify_bytes(
        url=url,
        data=data[:4096],
        content_type=info.content_type,
        http_status=meta.get("status_code"),
        final_url=meta.get("final_url") or url,
        text_preview=text_preview,
    )
    info.is_real_pdf = classification.is_real_pdf
    info.failure_type = classification.failure_type

    if classification.detected_type == "html":
        info.source_type = "html_fallback"
        html = text_preview or data.decode("utf-8", errors="ignore")
        login_signal = detect_login_requirements(html, url)
        if login_signal.access_type != "public":
            info.detected_actions.append({
                "action_type": login_signal.access_type,
                "required_items": login_signal.required_items,
                "data_access": login_signal.data_access,
                "automation_possible": login_signal.automation_possible,
                "next_action": login_signal.action,
                "confidence": login_signal.confidence,
                "signals": login_signal.signals,
            })
        html_info = parse_html(html)
        info.tender_ref = html_info.tender_ref
        info.tender_date = html_info.tender_date
        info.closing_date = html_info.closing_date
        info.qty = html_info.qty
        info.unit = html_info.unit
        if html_info.amount:
            try:
                info.total_price_inr = float(html_info.amount)
            except ValueError:
                pass
        info.product_description = html_info.description
        return parse_textual_content(info, html_info.description)

    if not classification.is_real_pdf:
        info.source_type = classification.detected_type
        info.failure_type = classification.failure_type or "not_a_pdf"
        return info

    info.source_type = "pdf"
    text, _tables = extract_text_and_tables(data)
    return parse_textual_content(info, text)
