"""Strict market-intelligence quality gate for ESKA gas equipment tenders."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict


def clean_join(*parts) -> str:
    return re.sub(r"\s+", " ", " ".join(str(p or "") for p in parts)).strip()

TARGET_RULES = [
    ("Domestic gas regulator", [r"domestic\s+(?:gas\s+)?regulator", r"png\s+regulator", r"house\s+service\s+regulator", r"service\s+governor", r"\b(?:10|25|50|100)\s*scmh\b.*regulator"]),
    ("Service / pressure regulator", [r"service\s+(?:pressure\s+)?regulator", r"gas\s+pressure\s+regulator", r"\bpressure\s+regulator\b", r"active\s+monitor", r"monitor\s+regulator"]),
    ("Industrial / commercial regulator", [r"industrial\s+regulator", r"commercial\s+regulator", r"c&i\s+regulator", r"pilot\s+operated\s+regulator", r"direct\s+acting\s+regulator"]),
    ("Regulating / metering station", [r"\bRMS\b", r"\bMRS\b", r"\bPRS\b", r"\bDRS\b", r"\bCGS\b", r"metering\s+(?:and\s+)?regulating", r"pressure\s+reducing\s+station", r"district\s+regulating\s+station", r"city\s+gate\s+station"]),
    ("Skid / gas train", [r"regulator\s+skid", r"metering\s+skid", r"skid\s+mounted", r"gas\s+train", r"filter\s+regulator", r"slam\s+shut.*regulator"]),
    ("Gas filter station / filter equipment", [r"gas\s+filter\s+station", r"filter\s+station", r"gas\s+filter\b", r"\bfilter\s+separator\b", r"cartridge\s+filter.*gas", r"strainer.*gas"]),
    ("Safety / shut-off equipment", [r"slam\s*shut", r"\bSSV\b", r"shut\s*off\s+valve", r"relief\s+valve", r"\bSRV\b", r"safety\s+shut\s*off"]),
]
SOFT_GAS_CONTEXT = [r"\bnatural\s+gas\b", r"\bcity\s+gas\b", r"\bCGD\b", r"\bPNG\b", r"\bgas\s+distribution\b", r"\bgas\s+pipeline\b"]
HARD_REJECT_RULES = [
    ("employment/corporate", r"career|recruitment|job\s+opening|investor|annual\s+report|csr|privacy|terms|contact\s+us|sitemap"),
    ("non-product service", r"housekeeping|security\s+service|manpower|catering|taxi|vehicle\s+hiring|canteen|gardening"),
    ("retail/cng station noise", r"cng\s+dispenser|dual\s+arm\s+dispenser|cng\s+compressor|compressor\s+oil|cascade|cylinder\s+cascade|cng\s+kit|lubricant"),
    ("civil/electrical only", r"street\s+light|furniture|printer|toner|computer|laptop|air\s+conditioner|painting\s+work"),
]
DOC_TYPE_RULES = [
    ("award", r"\bAOC\b|award\s+of\s+contract|awarded|award\s+result|successful\s+bidder"),
    ("loa", r"\bLOA\b|letter\s+of\s+award"),
    ("foa", r"\bFOA\b|fax\s+of\s+acceptance"),
    ("po_work_order", r"purchase\s+order|work\s+order|contract\s+order"),
    ("boq", r"\bBOQ\b|bill\s+of\s+quantities|price\s+schedule|schedule\s+of\s+rates"),
    ("tender", r"\bNIT\b|notice\s+inviting\s+tender|request\s+for\s+quotation|\bRFQ\b|\bRFP\b|\bEOI\b"),
    ("corrigendum", r"corrigendum|amendment|reply\s+to\s+bidders|pre-?bid"),
]

@dataclass
class MarketQuality:
    quality_status: str
    market_relevance: str
    target_confidence: str
    equipment_segment: str
    document_type: str
    matched_terms: list[str]
    reject_reasons: list[str]
    extraction_scope: str = "market_intelligence_only"
    excluded_scope: str = "no_bid_or_offer_submission_automation"
    def to_dict(self) -> dict:
        return asdict(self)


def detect_document_type(text: str) -> str:
    for doc_type, pat in DOC_TYPE_RULES:
        if re.search(pat, text or "", re.I):
            return doc_type
    return "unknown"


def classify_market_record(text: str, equipment_relevance: str | None = None, source_url: str = "") -> MarketQuality:
    hay = clean_join(text, source_url)
    doc_type = detect_document_type(hay)
    target_hits = []
    for label, patterns in TARGET_RULES:
        if any(re.search(p, hay, re.I) for p in patterns):
            target_hits.append(label)
    reject_reasons = [label for label, pat in HARD_REJECT_RULES if re.search(pat, hay, re.I)]
    if reject_reasons and not target_hits:
        return MarketQuality("non_target", "Irrelevant", "Medium", "Irrelevant / non-target", doc_type, [], reject_reasons)
    if target_hits:
        uniq = list(dict.fromkeys(target_hits))
        return MarketQuality("market_target", "High", "High" if len(uniq) >= 2 else "Medium", uniq[0], doc_type, uniq[:8], reject_reasons)
    if any(re.search(p, hay, re.I) for p in SOFT_GAS_CONTEXT) or equipment_relevance in {"High", "Medium"}:
        return MarketQuality("needs_review", "Medium", "Low", "Gas-related / review", doc_type, ["gas_context"], reject_reasons)
    return MarketQuality("non_target", "Low", "Low", "Unclassified", doc_type, [], reject_reasons)


def is_market_target(text: str, source_url: str = "") -> bool:
    return classify_market_record(text, source_url=source_url).quality_status == "market_target"
