"""Rule-based gas equipment classifier for ESKA market intelligence."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict

@dataclass
class EquipmentClassification:
    segment: str = "Unclassified"; equipment_type: str = "unknown"; relevance: str = "Low"; confidence: str = "Low"; matched_terms: list[str] | None = None
    def to_dict(self) -> dict:
        d = asdict(self); d["matched_terms"] = self.matched_terms or []; return d

RULES = [
    ("Domestic gas regulator","domestic_regulator","High",[r"domestic\s+(gas\s+)?regulator",r"png\s+regulator",r"house\s+service\s+regulator",r"service\s+governor"]),
    ("Service regulator","service_regulator","High",[r"service\s+(pressure\s+)?regulator",r"customer\s+regulator",r"\b10\s*scmh\b.*regulator",r"\b25\s*scmh\b.*regulator",r"\b50\s*scmh\b.*regulator",r"\b100\s*scmh\b.*regulator"]),
    ("Pressure regulator","pressure_regulator","High",[r"gas\s+pressure\s+regulator",r"\bpressure\s+regulator\b",r"regulator\s+with\s+slam",r"active\s+monitor",r"monitor\s+regulator"]),
    ("Industrial regulator","industrial_regulator","High",[r"industrial\s+regulator",r"commercial\s+regulator",r"c&i\s+regulator",r"pilot\s+operated\s+regulator",r"direct\s+acting\s+regulator"]),
    ("Regulating station","station","High",[r"\bPRS\b",r"\bDRS\b",r"\bMRS\b",r"\bRMS\b",r"\bCGS\b",r"metering\s+(and\s+)?regulating",r"pressure\s+reducing\s+station",r"district\s+regulating\s+station",r"city\s+gate\s+station"]),
    ("Skid / gas train","skid","High",[r"regulator\s+skid",r"metering\s+skid",r"gas\s+train",r"filter\s+regulator",r"skid\s+mounted"]),
    ("Gas filter station","filter_station","High",[r"gas\s+filter\s+station",r"filter\s+station",r"gas\s+filter\b",r"filter\s+separator",r"cartridge\s+filter.*gas",r"strainer.*gas"]),
    ("Safety / shut-off equipment","safety_valve","Medium",[r"slam\s+shut",r"\bSSV\b",r"shut\s*off\s+valve",r"relief\s+valve",r"\bSRV\b",r"safety\s+shut\s*off"]),
    ("Gas metering equipment","metering","Medium",[r"turbine\s+meter",r"rotary\s+meter",r"rpd\s+meter",r"ultrasonic\s+meter"]),
]
IRRELEVANT = [r"cng\s+vehicle",r"cng\s+kit",r"cng\s+dispenser",r"dual\s+arm\s+dispenser",r"lubricant",r"cylinder\s+cascade",r"compressor\s+oil",r"\bcompressor\b",r"manpower",r"security\s+service",r"housekeeping",r"civil\s+work",r"catering",r"annual\s+report",r"investor",r"career",r"csr",r"privacy",r"tender\s+fee"]

def classify_equipment(text: str) -> EquipmentClassification:
    hay = (text or "").lower(); target_hits = []
    for segment, eq_type, relevance, patterns in RULES:
        hits = [p for p in patterns if re.search(p, hay, re.I)]
        if hits: target_hits.append((segment, eq_type, relevance, hits))
    if target_hits:
        segment, eq_type, relevance, hits = target_hits[0]
        return EquipmentClassification(segment, eq_type, relevance, "High" if len(hits) >= 2 or len(target_hits) >= 2 else "Medium", hits[:6])
    irrelevant_terms = [pat for pat in IRRELEVANT if re.search(pat, hay, re.I)]
    if irrelevant_terms: return EquipmentClassification("Irrelevant / non-target", "irrelevant", "Irrelevant", "Medium", irrelevant_terms[:5])
    if re.search(r"\bgas\b|natural\s+gas|city\s+gas|cgd|png|cng", hay, re.I): return EquipmentClassification("Gas-related / review", "gas_related", "Medium", "Low", ["gas-related"])
    return EquipmentClassification()
