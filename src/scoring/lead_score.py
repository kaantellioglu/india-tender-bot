"""Lead priority scoring with strict market-intelligence quality gate."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from ..classifiers.gas_equipment_classifier import classify_equipment
from ..quality.market_filter import classify_market_record

@dataclass
class LeadScore:
    score: int; priority: str; reasons: list[str]; equipment_segment: str; equipment_type: str; equipment_relevance: str; confidence: str; quality_status: str = "needs_review"; document_type: str = "unknown"
    def to_dict(self) -> dict: return asdict(self)

POSITIVE_RULES = [(30,r"\b(loa|foa|aoc|award|awarded|successful bidder|letter of award|work order|purchase order)\b","award/result signal"),(25,r"\b(boq|bill of quantities|price schedule|quoted amount|contract value|order value)\b","commercial table signal"),(25,r"domestic\s+(gas\s+)?regulator|service\s+regulator|pressure\s+regulator|gas\s+pressure\s+regulator","target regulator keyword"),(25,r"\b(PRS|DRS|MRS|RMS|CGS)\b|metering\s+skid|regulator\s+skid|gas\s+train|filter\s+station","station/skid/filter keyword"),(15,r"\b(qty|quantity|nos|no\.|sets|units|pcs|each)\b","quantity signal"),(15,r"\b(inr|rs\.?|amount|price|quoted|contract\s+value)\b","commercial/price signal"),(10,r"tender\s*(no|ref)|bid\s*(no|id)|rfq|rfp|nit|eoi","tender reference signal")]
NEGATIVE_RULES = [(-60,r"career|job|recruitment|investor|annual report|csr|privacy|terms|contact us|sitemap","website noise"),(-45,r"vendor registration|supplier registration|login|password|captcha|tender fee|emd","access/fee page"),(-40,r"manpower|housekeeping|security service|catering|vehicle hiring|taxi|cng dispenser|compressor|cascade","non-target service/product")]

def score_text(text: str, file_type: str = "", matched_keyword: str = "") -> LeadScore:
    hay = f"{text or ''} {file_type or ''} {matched_keyword or ''}"
    score, reasons = 0, []
    eq = classify_equipment(hay); mq = classify_market_record(hay, equipment_relevance=eq.relevance)
    if mq.quality_status == "market_target": score += 35; reasons.append(f"quality:market_target:{mq.equipment_segment}")
    elif mq.quality_status == "needs_review": score += 8; reasons.append("quality:needs_review")
    else: score -= 55; reasons.append("quality:non_target")
    if eq.relevance == "High": score += 30; reasons.append(f"equipment:{eq.segment}")
    elif eq.relevance == "Medium": score += 10; reasons.append(f"equipment:{eq.segment}")
    elif eq.relevance == "Irrelevant": score -= 50; reasons.append("irrelevant_equipment")
    for pts, pat, reason in POSITIVE_RULES:
        if re.search(pat, hay, re.I): score += pts; reasons.append(reason)
    for pts, pat, reason in NEGATIVE_RULES:
        if re.search(pat, hay, re.I): score += pts; reasons.append(reason)
    if mq.quality_status == "non_target": score = min(score, 20)
    score = max(0, min(100, score))
    priority = "High" if score >= 70 and mq.quality_status == "market_target" else "Medium" if score >= 40 and mq.quality_status in {"market_target","needs_review"} else "Low"
    return LeadScore(score, priority, reasons[:14], mq.equipment_segment or eq.segment, eq.equipment_type, eq.relevance, "High" if mq.quality_status == "market_target" and score >= 70 else eq.confidence, mq.quality_status, mq.document_type)
