"""
Indirilen ihale/AOC/LOA PDF'lerinden yapisal veri cikarimi.

Hedef alanlar (04 Tender Register sekmesindeki kolonlara karsilik gelir):
- tender_ref   : ihale/LOA/FOA numarasi
- qty          : miktar (adet/set)
- unit_price   : INR birim fiyat (varsa)
- total_price  : INR toplam fiyat (varsa)
- winner       : kazanan firma (AOC/LOA belgelerinde)

PDF'ler cok farkli formatlarda oldugundan (bazan tablo, bazan duz metin,
bazan taranmis/OCR gerektiren), burada REGEX tabanli, "best effort" bir
cikarim yapilir. Guven duzeyi dusukse Excel'e "Confidence: Low" olarak
yazilir ve manuel kontrol icin isaretlenir.
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
    r"(LOA[\s_/-]?\d{6,})",
    r"(FOA[\s_/-]?\d{6,})",
    r"(AOC[\s_/-]?\d{6,})",
    r"(Tender\s*(?:No\.?|Ref\.?)[:\s]*[A-Za-z0-9/\-_.]+)",
    r"([A-Z]{2,10}/[A-Z0-9\-]+/\d{4}[-/]\d{2,4}/\d+)",  # GASONET/C&P-GSL/... tarzi
]

QTY_PATTERNS = [
    r"(?:Qty|Quantity)[:\s]*([\d,]+)\s*(nos|sets?|units?|pcs)?",
]

PRICE_PATTERNS = [
    r"(?:Total|Grand Total|Basic\s*(?:Price|Amount))[:\s]*(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)",
    r"(?:Unit\s*Price)[:\s]*(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)",
]

WINNER_PATTERNS = [
    r"(?:awarded to|M/s\.?|Successful Bidder[:\s]*)\s*([A-Z][A-Za-z0-9 &.,\-]{3,60}(?:Ltd|Limited|Pvt\.? Ltd\.?|Inc\.?)?)",
]


@dataclass
class ExtractedTenderInfo:
    source_url: str
    tender_ref: Optional[str] = None
    qty: Optional[str] = None
    unit: Optional[str] = None
    total_price_inr: Optional[float] = None
    winner: Optional[str] = None
    confidence: str = "Low"
    text_excerpt: str = ""


def download_pdf(url: str, timeout: int = 30) -> Optional[bytes]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 ESKA-TenderBot/1.0"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200 and resp.headers.get("Content-Type", "").lower().find("pdf") != -1 or url.lower().endswith(".pdf"):
            return resp.content
        logger.warning("PDF indirilemedi (status=%s): %s", resp.status_code, url)
    except requests.RequestException as exc:
        logger.warning("PDF indirme hatasi: %s (%s)", url, exc)
    return None


def extract_text(pdf_bytes: bytes, max_pages: int = 15) -> str:
    text_chunks = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                page_text = page.extract_text() or ""
                text_chunks.append(page_text)
    except Exception as exc:  # pdfplumber pek cok farkli hata firlatabilir
        logger.warning("PDF metin cikarimi basarisiz: %s", exc)
    return "\n".join(text_chunks)


def _first_match(patterns: list[str], text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def parse_tender_pdf(url: str) -> ExtractedTenderInfo:
    info = ExtractedTenderInfo(source_url=url)

    pdf_bytes = download_pdf(url)
    if not pdf_bytes:
        return info

    text = extract_text(pdf_bytes)
    info.text_excerpt = text[:500]

    info.tender_ref = _first_match(TENDER_REF_PATTERNS, text)

    qty_match = re.search(QTY_PATTERNS[0], text, flags=re.IGNORECASE)
    if qty_match:
        info.qty = qty_match.group(1).replace(",", "")
        info.unit = qty_match.group(2) or ""

    price_raw = _first_match(PRICE_PATTERNS, text)
    if price_raw:
        try:
            info.total_price_inr = float(price_raw.replace(",", ""))
        except ValueError:
            pass

    info.winner = _first_match(WINNER_PATTERNS, text)

    # Basit guven skoru: ne kadar alan doldu?
    filled = sum(bool(x) for x in [info.tender_ref, info.qty, info.total_price_inr, info.winner])
    info.confidence = {0: "Low", 1: "Low", 2: "Medium", 3: "Medium", 4: "High"}[filled]

    return info
