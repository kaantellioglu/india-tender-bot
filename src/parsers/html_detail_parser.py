"""Best-effort extraction from HTML tender list/detail pages."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional

from bs4 import BeautifulSoup


@dataclass
class HtmlTenderInfo:
    tender_ref: Optional[str] = None
    tender_date: Optional[str] = None
    closing_date: Optional[str] = None
    title: str = ""
    description: str = ""
    buyer: str = ""
    qty: Optional[str] = None
    unit: Optional[str] = None
    amount: Optional[str] = None
    source_type: str = "html"
    confidence: str = "Low"

    def to_dict(self) -> dict:
        return asdict(self)


DATE_PATTERNS = [
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
]
TENDER_REF_PATTERNS = [
    r"(?:Tender\s*(?:No\.?|Ref\.?|ID)|Bid\s*(?:No\.?|ID)|RFQ\s*(?:No\.?)?|NIT\s*(?:No\.?)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/_.\-]{4,})",
    r"\b([A-Z]{2,10}/[A-Z0-9_./\-]{5,}/\d{2,4}[A-Z0-9_./\-]*)\b",
]
QTY_RE = re.compile(r"(?:Qty|Quantity)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(nos|sets?|units?|pcs|each)?", re.I)
AMOUNT_RE = re.compile(r"(?:INR|Rs\.?|Amount|Value|Total)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)", re.I)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_date_near(label: str, text: str) -> Optional[str]:
    idx = text.lower().find(label.lower())
    if idx >= 0:
        chunk = text[idx:idx + 180]
        for pat in DATE_PATTERNS:
            m = re.search(pat, chunk, re.I)
            if m:
                return m.group(1)
    return None


def first_match(patterns: list[str], text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return None


def parse_html_text(text: str, fallback_title: str = "") -> HtmlTenderInfo:
    t = clean_text(text)
    info = HtmlTenderInfo(title=clean_text(fallback_title), description=t[:600])
    info.tender_ref = first_match(TENDER_REF_PATTERNS, t)
    info.tender_date = extract_date_near("tender date", t) or extract_date_near("start date", t) or first_match(DATE_PATTERNS, t)
    info.closing_date = (
        extract_date_near("closing date", t)
        or extract_date_near("due date", t)
        or extract_date_near("last date", t)
        or extract_date_near("submission deadline", t)
        or extract_date_near("end date", t)
    )
    q = QTY_RE.search(t)
    if q:
        info.qty = q.group(1).replace(",", "")
        info.unit = q.group(2) or ""
    a = AMOUNT_RE.search(t)
    if a:
        info.amount = a.group(1).replace(",", "")
    filled = sum(bool(x) for x in [info.tender_ref, info.tender_date, info.closing_date, info.qty, info.amount])
    info.confidence = "High" if filled >= 4 else "Medium" if filled >= 2 else "Low"
    return info


def parse_html(html: str, fallback_title: str = "") -> HtmlTenderInfo:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = fallback_title or clean_text((soup.title.get_text(" ") if soup.title else ""))
    text = soup.get_text(" ")
    return parse_html_text(text, title)
