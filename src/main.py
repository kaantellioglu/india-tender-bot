"""ESKA Global Gas Tender Bot - main runner."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .portal_loader import load_portals, load_keywords
from .scrapers import get_scraper, TenderLead
from .parsers.pdf_parser import parse_tender_pdf, ExtractedTenderInfo
from .storage.excel_store import update_workbook
from .notifier.notify import notify_new_tenders
from .diagnostics.source_failure import DiagnosticRecorder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("tender_bot")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = ROOT / "data" / "India_Procurement_Intelligence_Database.xlsx"


def _pdf_parse_priority(lead: TenderLead) -> tuple[int, int]:
    priority_rank = {"High": 0, "Medium": 1, "Low": 2}.get(lead.extra.get("priority", "Low"), 2)
    score = int(lead.extra.get("lead_score") or 0)
    return (priority_rank, -score)


def run(workbook_path: Path, tiers: list[str] | None, max_pdf_parses: int = 120) -> None:
    keywords = load_keywords()
    portals = load_portals(only_enabled=True, tiers=tiers)
    diagnostics = DiagnosticRecorder()
    logger.info("%d portal taranacak (tiers=%s)", len(portals), tiers or "hepsi")

    all_leads: list[TenderLead] = []
    for portal in portals:
        scraper = get_scraper(portal, keywords, diagnostics=diagnostics)
        try:
            leads = scraper.fetch_leads()
        except Exception as exc:
            logger.error("%s taranirken hata: %s", portal["name"], exc)
            diagnostics.record_failure(
                portal=portal,
                url=portal.get("tender_search_url") or portal.get("website") or "",
                failure_type="scraper_exception",
                action_required="scraper_rule_review",
                retry_strategy="create_or_update_portal_rule",
                note=str(exc)[:500],
            )
            leads = []
        all_leads.extend(leads)

    logger.info("Toplam %d aday ihale/duyuru bulundu (tum portallar)", len(all_leads))

    extracted_by_url: dict[str, ExtractedTenderInfo] = {}
    doc_leads = [l for l in all_leads if l.file_type in {"pdf", "doc", "xls"}]
    doc_leads = sorted(doc_leads, key=_pdf_parse_priority)[:max_pdf_parses]
    logger.info("%d dokuman icerik analizi icin isleniyor", len(doc_leads))
    for lead in doc_leads:
        try:
            info = parse_tender_pdf(lead.url)
            extracted_by_url[lead.url] = info
            if info.failure_type and diagnostics:
                diagnostics.record_failure(
                    portal={"id": lead.portal_id, "name": lead.portal_name},
                    url=lead.url,
                    failure_type=info.failure_type,
                    content_type=info.content_type,
                    action_required="document_parse_review" if info.failure_type.startswith("not_") else "review",
                    retry_strategy="html_fallback_or_manual_download" if info.source_type == "html_fallback" else "parser_rule_update",
                    signals=[info.source_type],
                )
            for action in info.detected_actions:
                diagnostics.record_action(
                    portal={"id": lead.portal_id, "name": lead.portal_name},
                    url=lead.url,
                    action_type=action.get("action_type", "manual_review"),
                    required_items=action.get("required_items", []),
                    data_access=action.get("data_access", "manual_review"),
                    automation_possible=action.get("automation_possible", "data_extraction_only"),
                    next_action=action.get("next_action", "Review source access for intelligence extraction"),
                    confidence=action.get("confidence", "Medium"),
                    signals=action.get("signals", []),
                )
        except Exception as exc:
            logger.warning("Dokuman parse hatasi (%s): %s", lead.url, exc)
            diagnostics.record_failure(
                portal={"id": lead.portal_id, "name": lead.portal_name},
                url=lead.url,
                failure_type="document_parse_exception",
                action_required="parser_rule_review",
                retry_strategy="improve_parser_or_source_review",
                note=str(exc)[:500],
            )

    if not workbook_path.exists():
        logger.error("Workbook bulunamadi: %s", workbook_path)
        sys.exit(1)

    result = update_workbook(workbook_path, all_leads, extracted_by_url)
    sample_titles = [l.title for l in all_leads[:15]]
    notify_new_tenders(result["new_register_rows"], result["new_price_rows"], sample_titles)
    logger.info("Tarama tamamlandi: %d yeni ihale, %d yeni fiyat kaydi eklendi", result["new_register_rows"], result["new_price_rows"])


def parse_args():
    parser = argparse.ArgumentParser(description="Global Gas Tender Intelligence Bot")
    parser.add_argument("--workbook", type=str, default=str(DEFAULT_WORKBOOK), help="Guncellenecek xlsx dosyasinin yolu")
    parser.add_argument("--tiers", nargs="*", default=None, help='Sadece belirli tier(lar)i tara')
    parser.add_argument("--max-pdf-parses", type=int, default=120, help="Bir calistirmada en fazla kac dokuman parse edilecek")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Path(args.workbook), args.tiers, args.max_pdf_parses)
