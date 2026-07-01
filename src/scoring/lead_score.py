"""Lead priority scoring.

Scores are deliberately transparent so sales/after-sales users can understand
why a tender was ranked high or low.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from ..classifiers.gas_equipment_classifier import classify_equipment


@dataclass
class LeadScore:
    score: int
    priority: str
    reasons: list[str]
    equipment_segment: str
    equipment_type: str
    equipment_relevance: str
    confidence: str

    def to_dict(self) -> dict:
        return asdict(self)


POSITIVE_RULES = [
    (35, r"\b(loa|foa|aoc|award|awarded|successful bidder|letter of award)\b", "award/result signal"),
    (30, r"domestic\s+(gas\s+)?regulator|service\s+regulator|pressure\s+regulator|gas\s+pressure\s+regulator", "target regulator keyword"),
    (25, r"\b(PRS|DRS|MRS|RMS|CGS)\b|metering\s+skid|regulator\s+skid|gas\s+train", "station/skid keyword"),
    (20, r"\b(pdf|doc|docx|xls|xlsx)\b", "document source"),
    (20, r"\b(qty|quantity|nos|no\.|sets|units|pcs|each)\b", "quantity signal"),
    (20, r"\b(inr|rs\.?|amount|price|boq|bill of quantities|quoted)\b", "commercial/price signal"),
    (15, r"tender\s*(no|ref)|bid\s*(no|id)|rfq|rfp|nit|eoi", "tender reference signal"),
    (10, r"closing\s+date|due\s+date|bid\s+submission|last\s+date", "closing date signal"),
]
NEGATIVE_RULES = [
    (-45, r"career|job|recruitment|investor|annual report|csr|privacy|terms|contact us", "website noise"),
    (-35, r"vendor registration|supplier registration|login|password|captcha", "access/action page"),
    (-25, r"manpower|housekeeping|security service|catering|vehicle hiring|taxi", "non-target service"),
]


def score_text(text: str, file_type: str = "", matched_keyword: str = "") -> LeadScore:
    hay = f"{text or ''} {file_type or ''} {matched_keyword or ''}"
    score = 0
    reasons: list[str] = []

    eq = classify_equipment(hay)
    if eq.relevance == "High":
        score += 35
        reasons.append(f"equipment:{eq.segment}")
    elif eq.relevance == "Medium":
        score += 15
        reasons.append(f"equipment:{eq.segment}")
    elif eq.relevance == "Irrelevant":
        score -= 50
        reasons.append("irrelevant_equipment")

    for pts, pat, reason in POSITIVE_RULES:
        if re.search(pat, hay, re.I):
            score += pts
            reasons.append(reason)
    for pts, pat, reason in NEGATIVE_RULES:
        if re.search(pat, hay, re.I):
            score += pts
            reasons.append(reason)

    score = max(0, min(100, score))
    if score >= 70:
        priority = "High"
    elif score >= 40:
        priority = "Medium"
    elif score <= 10 or eq.relevance == "Irrelevant":
        priority = "Low"
    else:
        priority = "Low"

    return LeadScore(
        score=score,
        priority=priority,
        reasons=reasons[:12],
        equipment_segment=eq.segment,
        equipment_type=eq.equipment_type,
        equipment_relevance=eq.relevance,
        confidence=eq.confidence,
    )
