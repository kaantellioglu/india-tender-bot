"""
Indirilen ihale/AOC/LOA PDF'lerinden yapisal veri cikarimi.

v2 iyilestirmeleri:
- PDF indirme kosulundaki operator onceligi hatasi duzeltildi.
- Metin + tablo extraction birlikte kullanilir.
- Tender ref, quantity, amount, winner, tender date, closing date ve product
  segment icin daha genis pattern seti kullanilir.
- Cikarilan bilgiler Excel'de mevcut satirlari da zenginlestirmek icin
  src/storage/excel_store.py tarafindan kullanilir.
"""
from __future__ import annotations

import io
import re
import logging
from dataclasses import dataclass
from typing import Optional

import requests
import pdfplumber

logger = logging.getLogger(__name__)

TENDER_REF_PATTERNS = [
    r"\b(LOA[\s_:/-]?[A-Za-z0-9/_\-.]{4,})",
    r"\b(FOA[\s_:/-]?[A-Za-z0-9/_\-.]{4,})",
    r"\b(AOC[\s_:/-]?[A-Za-z0-9/_\-.]{4,})",
    r"\b(?:Tender|Bid|RFQ|RFP|EOI|NIT)\s*(?:No\.?|Ref\.?|Number)?\s*[:#-]?\s*([A-Za-z0-9/_\-.]{5,})",
    r"\b([A-Z]{2,12}/[A-Z0-9][A-Z0-9/_\-.]{4,})\b",
]

DATE_PATTERNS = [
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4})\b",
]

TENDER_DATE_HINTS = ["tender date", "date of tender", "nit date", "issue date", "published date"]
CLOSING_DATE_HINTS = ["closing date", "due date", "last date", "bid end date", "submission end", "document download end"]

QTY_PATTERNS = [
    r"(?:Qty|Quantity|QTY\.?)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(nos?\.?|sets?|units?|pcs|pieces|each|ea)?",
    r"([\d,]+)\s*(nos?\.?|sets?|units?|pcs|pieces)\s+(?:of\s+)?(?:domestic|service|commercial|industrial|pressure|gas)?\s*regulators?",
    r"(?:Total\s+Quantity)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
]

PRICE_PATTERNS = [
    r"(?:Grand\s+Total|Total\s+Amount|Total\s+Price|Basic\s*(?:Price|Amount)|Awarded\s+Value|Contract\s+Value|Total\s+Accepted\s+Amount)\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d+)?)",
    r"(?:Unit\s*(?:Price|Rate)|Rate\s+per\s+unit|Basic\s+Rate)\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d+)?)",
    r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d+)?)",
]

WINNER_PATTERNS = [
    r"(?:awarded\s+to|awardee|successful\s+bidder|l1\s+bidder|selected\s+bidder|vendor\s+name)\s*[:\-]?\s*(M/s\.?\s*)?([A-Z][A-Za-z0-9 &.,()\-]{3,90}(?:Ltd|Limited|Pvt\.?\s*Ltd\.?|Private Limited|LLP|Inc\.?|Corporation)?)",
    r"\bM/s\.?\s+([A-Z][A-Za-z0-9 &.,()\-]{3,90}(?:Ltd|Limited|Pvt\.?\s*Ltd\.?|Private Limited|LLP|Inc\.?|Corporation)?)",
]

PRODUCT_HINTS = [
    ("Domestic regulator", ["domestic regulator", "png regulator", "household regulator"]),
    ("Service regulator", ["service regulator", "customer regulator"]),
    ("Commercial regulator", ["commercial regulator", "c&i regulator", "industrial & commercial"]),
    ("Industrial regulator", ["industrial regulator", "pilot operated regulator"]),
    ("Metering skid", ["metering skid", "metering and regulating", "rms", "mrs"]),
    ("PRS / DRS / FRS", ["prs", "drs", "frs", "pressure reducing station", "field regulating station"]),
    ("Slam shut / SSV", ["slam shut", "ssv", "shut off valve"]),
    ("Relief valve", ["relief valve", "srv"]),
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
    unit_price_inr: Optional[float] = None
    winner: Optional[str] = None
    product_segment: Optional[str] = None
    confidence: str = "Low"
    text_excerpt: str = ""


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ESKA-TenderBot/2.0"
        ),
        "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def download_pdf(url: str, timeout: int = 35) -> Optional[bytes]:
    try:
        resp = requests.get(url, headers=_headers(), timeout=timeout, allow_redirects=True)
        content_type = resp.headers.get("Content-Type", "").lower()
        is_pdf_like = "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")
        if resp.status_code == 200 and is_pdf_like:
            return resp.content
        logger.warning("PDF indirilemedi (status=%s, content-type=%s): %s", resp.status_code, content_type, url)
    except requests.RequestException as exc:
        logger.warning("PDF indirme hatasi: %s (%s)", url, exc)
    return None


def extract_text(pdf_bytes: bytes, max_pages: int = 20) -> str:
    text_chunks: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text() or ""
                if page_text:
                    text_chunks.append(page_text)

                # Tablo metinlerini de düz metne ekle.
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                for table in tables:
                    for row in table:
                        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                        if cells:
                            text_chunks.append(" | ".join(cells))
    except Exception as exc:
        logger.warning("PDF metin cikarimi basarisiz: %s", exc)
    return "\n".join(text_chunks)


def _first_match(patterns: list[str], text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            # Winner pattern'lerinde 2. grup firma olabilir.
            groups = [g for g in m.groups() if g]
            if groups:
                return groups[-1].strip()
            return m.group(0).strip()
    return None


def _parse_amount(raw: str | None) -> Optional[float]:
    if not raw:
        return None
    cleaned = raw.replace(",", "").replace("₹", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _date_near_hint(text: str, hints: list[str]) -> Optional[str]:
    low = text.lower()
    for hint in hints:
        idx = low.find(hint.lower())
        if idx == -1:
            continue
        chunk = text[idx: idx + 220]
        value = _first_match(DATE_PATTERNS, chunk)
        if value:
            return value
    return _first_match(DATE_PATTERNS, text)


def _classify_product(text: str) -> Optional[str]:
    low = text.lower()
    for segment, hints in PRODUCT_HINTS:
        if any(h in low for h in hints):
            return segment
    return None


def parse_tender_pdf(url: str) -> ExtractedTenderInfo:
    info = ExtractedTenderInfo(source_url=url)

    pdf_bytes = download_pdf(url)
    if not pdf_bytes:
        return info

    text = extract_text(pdf_bytes)
    compact_text = re.sub(r"\s+", " ", text or "").strip()
    info.text_excerpt = compact_text[:700]

    if not compact_text:
        return info

    info.tender_ref = _first_match(TENDER_REF_PATTERNS, compact_text)
    info.tender_date = _date_near_hint(compact_text, TENDER_DATE_HINTS)
    info.closing_date = _date_near_hint(compact_text, CLOSING_DATE_HINTS)
    info.product_segment = _classify_product(compact_text)

    qty_raw = _first_match(QTY_PATTERNS, compact_text)
    if qty_raw:
        # qty pattern'lerinde bazen unit group'u son grup olarak gelir; ayikla.
        m = re.search(QTY_PATTERNS[0], compact_text, flags=re.IGNORECASE)
        if m:
            info.qty = (m.group(1) or "").replace(",", "")
            info.unit = m.group(2) or ""
        else:
            info.qty = qty_raw.replace(",", "")

    price_values = []
    for pat in PRICE_PATTERNS:
        for m in re.finditer(pat, compact_text, flags=re.IGNORECASE):
            amount = _parse_amount(m.group(1))
            if amount is not None:
                price_values.append(amount)
    if price_values:
        # En yuksek deger genellikle toplam/contract value, en dusuk unit rate olabilir.
        info.total_price_inr = max(price_values)
        if len(price_values) > 1:
            info.unit_price_inr = min(v for v in price_values if v > 0)

    info.winner = _first_match(WINNER_PATTERNS, compact_text)

    filled = sum(bool(x) for x in [
        info.tender_ref, info.tender_date, info.closing_date,
        info.qty, info.total_price_inr, info.winner, info.product_segment
    ])
    if filled >= 5:
        info.confidence = "High"
    elif filled >= 3:
        info.confidence = "Medium"
    elif filled >= 1:
        info.confidence = "Low"
    else:
        info.confidence = "None"

    return info
