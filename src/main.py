"""
ESKA India Tender Bot - ana calistirma noktasi.

Kullanim:
    python -m src.main
    python -m src.main --tiers "Tier 1" "Tier 2"
    python -m src.main --workbook data/India_Procurement_Intelligence_Database.xlsx

Akis:
1. config/portals.yaml + config/keywords.yaml yuklenir
2. Her portal icin uygun scraper calistirilir -> TenderLead listesi
3. PDF uzantili lead'ler icin pdf_parser ile fiyat/miktar/kazanan cikarimi denenir
4. Sonuclar mevcut xlsx semasina (Tender Register / Price Intelligence) eklenir
5. Yeni kayit varsa e-posta/Telegram bildirimi gonderilir
"""
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tender_bot")

DEFAULT_WORKBOOK = Path(__file__).resolve().parent.parent / "data" / "India_Procurement_Intelligence_Database.xlsx"


def run(workbook_path: Path, tiers: list[str] | None, max_pdf_parses: int = 40) -> None:
    keywords = load_keywords()
    portals = load_portals(only_enabled=True, tiers=tiers)
    logger.info("%d portal taranacak (tiers=%s)", len(portals), tiers or "hepsi")

    all_leads: list[TenderLead] = []
    for portal in portals:
        scraper = get_scraper(portal, keywords)
        try:
            leads = scraper.fetch_leads()
        except Exception as exc:  # tek bir portalin hatasi tum taramayi durdurmasin
            logger.error("%s taranirken hata: %s", portal["name"], exc)
            leads = []
        all_leads.extend(leads)

    logger.info("Toplam %d aday ihale/duyuru bulundu (tum portallar)", len(all_leads))

    # PDF olanlardan fiyat/miktar/kazanan cikarmayi dene (maliyet/sure icin sinirli sayida)
    extracted_by_url: dict[str, ExtractedTenderInfo] = {}
    pdf_leads = [l for l in all_leads if l.file_type == "pdf"][:max_pdf_parses]
    logger.info("%d PDF icerik analizi icin isleniyor", len(pdf_leads))
    for lead in pdf_leads:
        try:
            info = parse_tender_pdf(lead.url)
            extracted_by_url[lead.url] = info
        except Exception as exc:
            logger.warning("PDF parse hatasi (%s): %s", lead.url, exc)

    if not workbook_path.exists():
        logger.error(
            "Workbook bulunamadi: %s\n"
            "Ilk calistirmadan once 'India_Procurement_Intelligence_Database.xlsx' "
            "dosyasini data/ klasorune kopyalayin (bkz. README).",
            workbook_path,
        )
        sys.exit(1)

    result = update_workbook(workbook_path, all_leads, extracted_by_url)

    sample_titles = [l.title for l in all_leads[:15]]
    notify_new_tenders(result["new_register_rows"], result["new_price_rows"], sample_titles)

    logger.info(
        "Tarama tamamlandi: %d yeni ihale, %d yeni fiyat kaydi eklendi",
        result["new_register_rows"], result["new_price_rows"],
    )


def parse_args():
    parser = argparse.ArgumentParser(description="ESKA India Tender Bot")
    parser.add_argument(
        "--workbook", type=str, default=str(DEFAULT_WORKBOOK),
        help="Guncellenecek xlsx dosyasinin yolu",
    )
    parser.add_argument(
        "--tiers", nargs="*", default=None,
        help='Sadece belirli tier(lar)i tara, orn: --tiers "Tier 1" "Tier 2"',
    )
    parser.add_argument(
        "--max-pdf-parses", type=int, default=40,
        help="Bir calistirmada en fazla kac PDF indirip parse edilecegi (varsayilan 40)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(Path(args.workbook), args.tiers, args.max_pdf_parses)
