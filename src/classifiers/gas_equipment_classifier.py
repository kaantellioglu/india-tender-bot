"""Rule-based gas equipment classifier.

The first production version should be auditable, not a black box. Rules can be
expanded later with country/portal specific dictionaries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict


@dataclass
class EquipmentClassification:
    segment: str = "Unclassified"
    equipment_type: str = "unknown"
    relevance: str = "Low"  # High/Medium/Low/Irrelevant
    confidence: str = "Low"
    matched_terms: list[str] | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["matched_terms"] = self.matched_terms or []
        return d


RULES = [
    ("Domestic regulator", "domestic_regulator", "High", [r"domestic\s+(gas\s+)?regulator", r"png\s+regulator", r"house\s+service\s+regulator", r"service\s+governor"]),
    ("Service regulator", "service_regulator", "High", [r"service\s+(pressure\s+)?regulator", r"customer\s+regulator", r"\b10\s*scmh\b", r"\b25\s*scmh\b", r"\b50\s*scmh\b", r"\b100\s*scmh\b"]),
    ("Pressure regulator", "pressure_regulator", "High", [r"gas\s+pressure\s+regulator", r"pressure\s+regulator", r"regulator\s+with\s+slam", r"active\s+monitor"]),
    ("Industrial regulator", "industrial_regulator", "High", [r"industrial\s+regulator", r"commercial\s+regulator", r"c&i\s+regulator"]),
    ("Regulating station", "station", "High", [r"\bPRS\b", r"\bDRS\b", r"\bMRS\b", r"\bRMS\b", r"metering\s+(and\s+)?regulating", r"pressure\s+reducing\s+station", r"district\s+regulating\s+station"]),
    ("Skid / gas train", "skid", "High", [r"regulator\s+skid", r"metering\s+skid", r"gas\s+train", r"filter\s+regulator", r"skid\s+mounted"]),
    ("Safety valve", "safety_valve", "Medium", [r"slam\s+shut", r"\bSSV\b", r"shut\s*off\s+valve", r"relief\s+valve", r"\bSRV\b"]),
    ("Metering", "metering", "Medium", [r"turbine\s+meter", r"rotary\s+meter", r"rpd\s+meter", r"ultrasonic\s+meter"]),
]

IRRELEVANT = [
    r"cng\s+vehicle", r"cng\s+kit", r"lubricant", r"cylinder\s+cascade", r"compressor\s+oil",
    r"manpower", r"security\s+service", r"housekeeping", r"civil\s+work", r"catering",
    r"annual\s+report", r"investor", r"career", r"csr", r"policy",
]


def classify_equipment(text: str) -> EquipmentClassification:
    hay = (text or "").lower()
    irrelevant_terms = []
    for pat in IRRELEVANT:
        if re.search(pat, hay, re.I):
            irrelevant_terms.append(pat)
    if irrelevant_terms:
        return EquipmentClassification(
            segment="Irrelevant / non-target",
            equipment_type="irrelevant",
            relevance="Irrelevant",
            confidence="Medium",
            matched_terms=irrelevant_terms[:5],
        )

    for segment, eq_type, relevance, patterns in RULES:
        hits = [p for p in patterns if re.search(p, hay, re.I)]
        if hits:
            confidence = "High" if len(hits) >= 2 else "Medium"
            return EquipmentClassification(segment, eq_type, relevance, confidence, hits[:5])

    if re.search(r"\bgas\b|natural\s+gas|city\s+gas|cgd|png|cng", hay, re.I):
        return EquipmentClassification("Gas-related / review", "gas_related", "Medium", "Low", ["gas-related"])
    return EquipmentClassification()
