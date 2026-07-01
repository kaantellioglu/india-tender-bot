"""Commercial-field extraction from tender/AOC/LOA/BOQ text."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from ..quality.market_filter import clean_join, classify_market_record, detect_document_type

@dataclass
class CommercialExtraction:
    qty: str | None = None
    unit: str | None = None
    total_price_inr: float | None = None
    unit_price_inr: float | None = None
    winner: str | None = None
    amount_label: str = ""
    document_type: str = "unknown"
    confidence: str = "Low"
    quality_status: str = "non_target"
    market_relevance: str = "Low"
    equipment_segment: str = ""
    matched_terms: list[str] | None = None
    reject_reasons: list[str] | None = None
    extraction_notes: list[str] | None = None
    def to_dict(self) -> dict:
        d = asdict(self)
        d["matched_terms"] = self.matched_terms or []
        d["reject_reasons"] = self.reject_reasons or []
        d["extraction_notes"] = self.extraction_notes or []
        return d

def _normalize_num(raw: str) -> float | None:
    s = re.sub(r"[^\d.,]", "", str(raw or "")).replace(",", "")
    try: return float(s) if s else None
    except ValueError: return None

def _money_to_inr(num: float, unit_word: str = "") -> float:
    u = (unit_word or "").lower().strip(".")
    if "crore" in u or u == "cr": return num * 10000000
    if "lakh" in u or "lac" in u or u in {"lk", "l"}: return num * 100000
    return num

def _valid_amount_context(chunk: str) -> bool:
    low = chunk.lower()
    bad = ["emd", "earnest money", "tender fee", "processing fee", "security deposit", "bank guarantee", "performance guarantee"]
    return not any(x in low for x in bad)

AMOUNT_PATTERNS = [
    ("award_value", r"(?:awarded\s+value|award\s+value|contract\s+value|order\s+value|loa\s+value|po\s+value)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\.?|lakh|lac|lakhs|lacs)?"),
    ("total_amount", r"(?:grand\s+total|total\s+amount|total\s+price|total\s+quoted\s+amount|basic\s+amount|basic\s+price)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\.?|lakh|lac|lakhs|lacs)?"),
    ("estimated_cost", r"(?:estimated\s+cost|estimate\s+value|tender\s+value|estimated\s+value)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\.?|lakh|lac|lakhs|lacs)?"),
    ("currency_near_total", r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crore|cr\.?|lakh|lac|lakhs|lacs)?\s*(?:only)?\s*(?:\(|-|:)?\s*(?:total|award|contract|order|quoted)?"),
]
QTY_PATTERNS = [
    r"(?:qty|quantity|qnty|total\s+quantity)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(nos?|no\.?s?|sets?|units?|pcs|each|lot|lots)?",
    r"\b([\d,]+)\s*(nos?|no\.?s?|sets?|units?|pcs|each)\s+(?:of\s+)?(?:domestic\s+gas\s+regulators?|service\s+regulators?|pressure\s+regulators?|gas\s+filters?|filter\s+stations?|rms|mrs|prs|drs|skids?)",
    r"(?:domestic\s+gas\s+regulators?|service\s+regulators?|pressure\s+regulators?|gas\s+filters?|filter\s+stations?|rms|mrs|prs|drs|skids?).{0,80}?\b([\d,]+)\s*(nos?|no\.?s?|sets?|units?|pcs|each)",
]
UNIT_PRICE_PATTERNS = [
    r"(?:unit\s+price|unit\s+rate|rate\s+per\s+unit|basic\s+rate)\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d+)?)",
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+no|per\s+nos|per\s+unit|each)",
]
WINNER_PATTERNS = [
    r"(?:awarded\s+to|awardee|successful\s+bidder|successful\s+tenderer|l1\s+bidder|contractor|supplier|vendor)\s*[:\-]?\s*(?:m/s\.?\s*)?([A-Z][A-Za-z0-9 &.,'\-()/]{3,100}(?:Ltd|Limited|Pvt\.?\s*Ltd\.?|LLP|Industries|Enterprises|Corporation|Company|Co\.|India)?)",
    r"(?:M/s\.?|M/S)\s+([A-Z][A-Za-z0-9 &.,'\-()/]{3,100}(?:Ltd|Limited|Pvt\.?\s*Ltd\.?|LLP|Industries|Enterprises|Corporation|Company|Co\.|India)?)",
]

def extract_quantity(text: str):
    for pat in QTY_PATTERNS:
        m = re.search(pat, text, re.I | re.S)
        if m: return (m.group(1) or "").replace(",", ""), (m.group(2) or "").replace(".", "")
    return None, None

def extract_amount(text: str):
    for label, pat in AMOUNT_PATTERNS:
        for m in re.finditer(pat, text, re.I | re.S):
            if not _valid_amount_context(text[max(0,m.start()-80):min(len(text),m.end()+80)]): continue
            num = _normalize_num(m.group(1)); unit = m.group(2) if len(m.groups()) >= 2 else ""
            if num is not None:
                amount = _money_to_inr(num, unit or "")
                if amount >= 1000: return amount, label
    return None, ""

def extract_unit_price(text: str):
    for pat in UNIT_PRICE_PATTERNS:
        m = re.search(pat, text, re.I | re.S)
        if m: return _normalize_num(m.group(1))
    return None

def extract_winner(text: str):
    for pat in WINNER_PATTERNS:
        m = re.search(pat, text, re.I | re.S)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .,-:")
            name = re.split(r"\s{2,}|(?:\s+for\s+)|(?:\s+against\s+)|(?:\s+vide\s+)", name)[0].strip(" .,-:")
            return name[:120]
    return None

def extract_commercial_info(text: str, source_url: str = "") -> CommercialExtraction:
    compact = clean_join(text)
    mq = classify_market_record(compact, source_url=source_url)
    qty, unit = extract_quantity(compact)
    total, label = extract_amount(compact)
    unit_price = extract_unit_price(compact)
    winner = extract_winner(compact)
    notes = []
    if unit_price is None and total is not None and qty:
        try:
            q = float(str(qty).replace(",", ""))
            if q > 0:
                unit_price = total / q
                notes.append("unit_price_calculated_total_div_qty")
        except Exception: pass
    filled = sum(bool(x) for x in [qty, total, unit_price, winner])
    confidence = "High" if mq.quality_status == "market_target" and filled >= 3 else "Medium" if mq.quality_status == "market_target" and filled >= 1 else "Low"
    return CommercialExtraction(qty, unit, total, unit_price, winner, label, detect_document_type(compact), confidence, mq.quality_status, mq.market_relevance, mq.equipment_segment, mq.matched_terms, mq.reject_reasons, notes)
