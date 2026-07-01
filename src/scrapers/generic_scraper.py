"""Generic scraper for public tender pages with strict market-intelligence filtering."""
from __future__ import annotations
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse
import yaml
from bs4 import BeautifulSoup, Tag
from .base_scraper import BaseScraper, TenderLead
from ..access.login_detector import detect_login_requirements
from ..parsers.html_detail_parser import parse_html_text, clean_text
from ..scoring.lead_score import score_text
from ..discovery.archive_discovery import discover_sources
from ..quality.market_filter import classify_market_record
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]; PORTAL_RULES_PATH = ROOT / "config" / "portal_rules.yaml"
STRONG_DOCUMENT_HINTS = ["nit","rfq","rfp","eoi","corrigendum","aoc","loa","foa","boq","tender no","tender ref","bid no","e-tender","award","letter of award","purchase order","work order","price schedule"]
DOC_EXTENSIONS = (".pdf",".doc",".docx",".xls",".xlsx",".csv"); DEFAULT_MAX_LEADS_PER_PORTAL = 120
NOISE_HINTS = ["contact us","privacy","terms","career","investor","annual report","sitemap","facebook","twitter","linkedin","youtube","copyright","about us","vendor registration","supplier registration","login","forgot password"]

def load_portal_rules() -> dict:
    if not PORTAL_RULES_PATH.exists(): return {}
    try:
        data = yaml.safe_load(PORTAL_RULES_PATH.read_text(encoding="utf-8")) or {}; return data.get("portals", data) or {}
    except Exception as exc:
        logger.warning("portal_rules.yaml okunamadi: %s", exc); return {}

def parent_context_text(a: Tag) -> str:
    for name in ["tr","li","article"]:
        p = a.find_parent(name)
        if p: return clean_text(p.get_text(" ", strip=True))
    for cls_hint in ["card","tender","row","item","notice","result"]:
        p = a.find_parent(class_=lambda c: c and cls_hint in str(c).lower())
        if p: return clean_text(p.get_text(" ", strip=True))
    return clean_text((a.parent.get_text(" ", strip=True) if a.parent else a.get_text(" ", strip=True)))

def infer_file_type(url: str) -> str:
    path = urlparse(url).path.lower().split("?")[0]
    if path.endswith(".pdf"): return "pdf"
    if path.endswith((".doc",".docx")): return "doc"
    if path.endswith((".xls",".xlsx",".csv")): return "xls"
    return "html"

class GenericScraper(BaseScraper):
    def fetch_leads(self) -> list[TenderLead]:
        candidates = []; rules = load_portal_rules().get(self.portal.get("id", ""), {})
        max_leads = int(rules.get("max_leads", DEFAULT_MAX_LEADS_PER_PORTAL)); noise_filters = [*NOISE_HINTS, *rules.get("noise_filters", [])]
        priority_keywords = [k.lower() for k in rules.get("priority_keywords", [])]; sources = discover_sources(self.portal, rules)
        if not sources: return candidates
        seen_urls = set(); usable_source_count = 0
        for source in sources:
            url = source.url; resp = self._get(url)
            if resp is None: continue
            usable_source_count += 1
            access_signal = detect_login_requirements(resp.text, url)
            if access_signal.access_type != "public" and self.diagnostics:
                self.diagnostics.record_action(portal=self.portal, url=url, action_type=access_signal.access_type, required_items=access_signal.required_items, data_access=access_signal.data_access, automation_possible=access_signal.automation_possible, next_action=access_signal.action, confidence=access_signal.confidence, signals=access_signal.signals)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip(); text = clean_text(a.get_text(" ", strip=True) or "")
                if not href or href.startswith("javascript:") or href.startswith("#") or href.lower().startswith("mailto:"): continue
                full_url = urljoin(resp.url or url, href)
                if full_url in seen_urls: continue
                row_text = parent_context_text(a); haystack = clean_text(f"{text} {href} {row_text} {source.source_kind}"); hay_low = haystack.lower()
                file_type = infer_file_type(full_url); is_document = file_type in {"pdf","doc","xls"}
                matched_kw = self._matches_keyword(haystack); strong_doc_hint = is_document and any(h in hay_low for h in STRONG_DOCUMENT_HINTS); priority_kw_hit = any(pk in hay_low for pk in priority_keywords)
                html_info = parse_html_text(row_text or haystack, fallback_title=text); tender_signal = bool(html_info.tender_ref or html_info.closing_date)
                archive_signal = source.source_kind in {"award_archive","award_or_archive","archive_guess"} and any(h in hay_low for h in ["aoc","loa","foa","award","work order","purchase order"])
                score = score_text(haystack, file_type=file_type, matched_keyword=matched_kw or ""); quality = classify_market_record(haystack, equipment_relevance=score.equipment_relevance, source_url=full_url)
                if any(n in hay_low for n in noise_filters) and quality.quality_status != "market_target": continue
                if quality.quality_status == "non_target" and not archive_signal: continue
                if not (matched_kw or priority_kw_hit or strong_doc_hint or tender_signal or archive_signal or quality.quality_status == "market_target"): continue
                if score.priority == "Low" and quality.quality_status != "market_target" and not archive_signal: continue
                seen_urls.add(full_url); title = text or html_info.title or row_text[:140] or full_url
                extra = {"source_type":"html_table" if row_text and row_text != text else "html_link","source_page_url":url,"source_page_kind":source.source_kind,"source_page_reason":source.reason,"row_text":row_text,"tender_ref":html_info.tender_ref,"tender_date":html_info.tender_date,"closing_date":html_info.closing_date,"html_confidence":html_info.confidence,"lead_score":score.score,"priority":score.priority,"score_reasons":score.reasons,"equipment_segment":score.equipment_segment,"equipment_type":score.equipment_type,"equipment_relevance":score.equipment_relevance,"quality_status":quality.quality_status,"market_relevance":quality.market_relevance,"target_confidence":quality.target_confidence,"document_type":quality.document_type,"matched_terms":quality.matched_terms,"reject_reasons":quality.reject_reasons,"extraction_scope":quality.extraction_scope,"excluded_scope":quality.excluded_scope}
                candidates.append(TenderLead(portal_id=self.portal["id"], portal_name=self.portal["name"], title=title[:300], url=full_url, matched_keyword=matched_kw, published_date=html_info.tender_date, file_type=file_type, raw_snippet=row_text or text, extra=extra))
        candidates.sort(key=lambda l: (0 if l.extra.get("quality_status") == "market_target" else 1 if l.extra.get("quality_status") == "needs_review" else 2, 0 if l.extra.get("priority") == "High" else 1 if l.extra.get("priority") == "Medium" else 2, -(l.extra.get("lead_score") or 0), 0 if l.extra.get("document_type") in {"award","loa","foa","po_work_order","boq"} else 1, 0 if l.file_type in {"pdf","doc","xls"} else 1))
        leads = candidates[:max_leads]; source_note = f"{usable_source_count}/{len(sources)} kaynak sayfasi"
        logger.info("%s: %d aday%s (%s)", self.portal["name"], len(leads), " bulundu" if len(candidates) <= max_leads else f" bulundu, ilk {max_leads} tanesi alindi", source_note)
        return leads
