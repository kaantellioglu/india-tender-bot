"""Tender document parser: PDF-first with HTML fallback and commercial extraction."""
from __future__ import annotations
import io, re, logging
from dataclasses import dataclass, field
from typing import Optional
import requests, pdfplumber
from ..access.content_classifier import classify_bytes
from ..access.login_detector import detect_login_requirements
from .html_detail_parser import parse_html, clean_text
from ..scoring.lead_score import score_text
from .commercial_extractor import extract_commercial_info

logger = logging.getLogger(__name__)
TENDER_REF_PATTERNS = [
    r"(?:Tender\s*(?:No\.?|Ref\.?|ID)|Bid\s*(?:No\.?|ID)|RFQ\s*(?:No\.?)?|NIT\s*(?:No\.?)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/_.\-]{4,})",
    r"(LOA[\s_/-]?\d{4,})", r"(FOA[\s_/-]?\d{4,})", r"(AOC[\s_/-]?\d{4,})",
    r"\b([A-Z]{2,12}/[A-Z0-9_.\-/]{5,}/\d{2,4}[A-Z0-9_.\-/]*)\b",
]
DATE_PATTERNS = [r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b", r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4})\b"]

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
    document_type: str = "unknown"
    quality_status: str = "non_target"
    market_relevance: str = "Low"
    target_terms: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    amount_label: str = ""
    extraction_notes: list[str] = field(default_factory=list)

def download_document(url: str, timeout: int = 30):
    meta = {"status_code": None, "content_type": "", "final_url": url}
    try:
        headers = {"User-Agent":"Mozilla/5.0 Chrome/124 Safari/537.36", "Accept":"application/pdf,text/html,*/*", "Accept-Language":"en-US,en;q=0.9,tr;q=0.7"}
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        meta = {"status_code": resp.status_code, "content_type": resp.headers.get("Content-Type", ""), "final_url": resp.url}
        if resp.status_code == 200: return resp.content, meta
        logger.warning("Dokuman indirilemedi (status=%s): %s", resp.status_code, url)
    except requests.RequestException as exc:
        meta["error"] = str(exc); logger.warning("Dokuman indirme hatasi: %s (%s)", url, exc)
    return None, meta

def extract_text_and_tables(pdf_bytes: bytes, max_pages: int = 35):
    text_chunks, tables = [], []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                text_chunks.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
                try:
                    for table in page.extract_tables() or []:
                        clean_table = [[clean_text(str(cell or "")) for cell in row] for row in table if row]
                        if clean_table: tables.append(clean_table)
                except Exception: pass
    except Exception as exc:
        logger.warning("PDF metin cikarimi basarisiz: %s", exc)
    table_text = "\n".join(" | ".join(row) for table in tables for row in table[:120])
    return "\n".join(text_chunks + [table_text]), tables

def first_match(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, flags=re.I|re.S)
        if m: return clean_text(m.group(1))
    return None

def date_near(labels, text):
    low = text.lower()
    for label in labels:
        idx = low.find(label.lower())
        if idx >= 0:
            d = first_match(DATE_PATTERNS, text[idx:idx+260])
            if d: return d
    return None

def parse_textual_content(info: ExtractedTenderInfo, text: str) -> ExtractedTenderInfo:
    compact = clean_text(text)
    info.text_excerpt = compact[:1200]
    info.tender_ref = first_match(TENDER_REF_PATTERNS, compact)
    info.tender_date = date_near(["tender date","date of tender","start date","published","issue date","document date"], compact) or first_match(DATE_PATTERNS, compact)
    info.closing_date = date_near(["closing date","due date","last date","end date","submission deadline","document download end date"], compact)
    comm = extract_commercial_info(compact, source_url=info.source_url)
    info.qty, info.unit, info.total_price_inr, info.unit_price_inr, info.winner = comm.qty, comm.unit, comm.total_price_inr, comm.unit_price_inr, comm.winner
    info.document_type, info.quality_status, info.market_relevance = comm.document_type, comm.quality_status, comm.market_relevance
    info.equipment_segment, info.target_terms, info.reject_reasons = comm.equipment_segment, comm.matched_terms or [], comm.reject_reasons or []
    info.amount_label, info.extraction_notes = comm.amount_label, comm.extraction_notes or []
    info.product_description = compact[:1000]
    score = score_text(compact, file_type=info.source_type, matched_keyword="")
    info.lead_score, info.priority, info.equipment_type = score.score, score.priority, score.equipment_type
    filled = sum(bool(x) for x in [info.tender_ref, info.tender_date, info.closing_date, info.qty, info.total_price_inr, info.winner])
    info.confidence = "High" if info.quality_status == "market_target" and filled >= 4 else "Medium" if info.quality_status == "market_target" and filled >= 2 else "Low"
    return info

def parse_tender_pdf(url: str) -> ExtractedTenderInfo:
    info = ExtractedTenderInfo(source_url=url)
    data, meta = download_document(url)
    info.content_type = meta.get("content_type", "") or ""
    if not data:
        info.failure_type = "download_failed"; return info
    try: text_preview = data[:12000].decode("utf-8", errors="ignore")
    except Exception: text_preview = ""
    classification = classify_bytes(url=url, data=data[:4096], content_type=info.content_type, http_status=meta.get("status_code"), final_url=meta.get("final_url") or url, text_preview=text_preview)
    info.is_real_pdf, info.failure_type = classification.is_real_pdf, classification.failure_type
    if classification.detected_type == "html":
        info.source_type = "html_fallback"; html = text_preview or data.decode("utf-8", errors="ignore")
        login_signal = detect_login_requirements(html, url)
        if login_signal.access_type != "public":
            info.detected_actions.append({"action_type": login_signal.access_type, "required_items": login_signal.required_items, "data_access": login_signal.data_access, "automation_possible": login_signal.automation_possible, "next_action": login_signal.action, "confidence": login_signal.confidence, "signals": login_signal.signals})
        html_info = parse_html(html)
        merged = " ".join(str(x or "") for x in [html_info.tender_ref, html_info.tender_date, html_info.closing_date, html_info.qty, html_info.amount, html_info.description])
        parsed = parse_textual_content(info, merged)
        parsed.tender_ref = parsed.tender_ref or html_info.tender_ref; parsed.tender_date = parsed.tender_date or html_info.tender_date; parsed.closing_date = parsed.closing_date or html_info.closing_date
        return parsed
    if not classification.is_real_pdf:
        info.source_type = classification.detected_type; info.failure_type = classification.failure_type or "not_a_pdf"; return info
    info.source_type = "pdf"
    text, _tables = extract_text_and_tables(data)
    return parse_textual_content(info, text)
