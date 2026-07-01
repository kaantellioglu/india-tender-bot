"""
Sonuclari, mevcut 'India_Procurement_Intelligence_Database.xlsx' ile AYNI
sema/sekmelerle guncellenen bir calisma dosyasina yazar.

Mantik:
- data/India_Procurement_Intelligence_Database.xlsx yoksa, ilk calistirmada
  kullanicidan/repodan bir kopya konur (bkz. README kurulum adimlari).
- '04 Tender Register' sekmesine yeni tespit edilen linkler/PDF'ler,
  ayni kolon sirasiyla, tekrar eden URL'ler HARIC eklenir.
- '06 Price Intelligence' sekmesine, PDF'den fiyat/miktar cikarilabilmisse
  ayni sekilde eklenir.
- Her calistirmada '08 Source Log' sekmesine bir satir (tarih, kac yeni
  kayit bulundu) eklenir.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

import openpyxl

from ..scrapers.base_scraper import TenderLead
from ..parsers.pdf_parser import ExtractedTenderInfo

logger = logging.getLogger(__name__)

TENDER_REGISTER_SHEET = "04 Tender Register"
PRICE_INTEL_SHEET = "06 Price Intelligence"
SOURCE_LOG_SHEET = "08 Source Log"

TENDER_REGISTER_HEADER_ROW = 3  # sekmedeki baslik satiri (1-indexed)
PRICE_INTEL_HEADER_ROW = 3


def _existing_urls(ws, url_col_idx: int, header_row: int) -> set[str]:
    urls = set()
    for row in ws.iter_rows(min_row=header_row + 1, max_col=url_col_idx, values_only=True):
        val = row[url_col_idx - 1]
        if val:
            urls.add(str(val).strip())
    return urls


def _next_tender_id(ws, id_col_idx: int, header_row: int, prefix: str = "T-") -> str:
    max_num = 0
    for row in ws.iter_rows(min_row=header_row + 1, max_col=id_col_idx, values_only=True):
        val = row[id_col_idx - 1]
        if val and str(val).startswith(prefix):
            try:
                num = int(str(val).replace(prefix, ""))
                max_num = max(max_num, num)
            except ValueError:
                continue
    return f"{prefix}{max_num + 1:04d}"


def update_workbook(
    workbook_path: str | Path,
    leads: Iterable[TenderLead],
    extracted_by_url: dict[str, ExtractedTenderInfo],
) -> dict:
    """
    workbook_path: mevcut/ana xlsx dosyasinin yolu (dogrudan uzerine yazilir;
                   otomasyonda her calistirmadan once git commit ile
                   versiyonlanmasi onerilir).
    leads: scraper'lardan gelen TenderLead listesi
    extracted_by_url: {lead.url: ExtractedTenderInfo} - PDF parse sonuclari

    Donen deger: {'new_register_rows': int, 'new_price_rows': int}
    """
    workbook_path = Path(workbook_path)
    wb = openpyxl.load_workbook(workbook_path)

    ws_reg = wb[TENDER_REGISTER_SHEET]
    ws_price = wb[PRICE_INTEL_SHEET]
    ws_log = wb[SOURCE_LOG_SHEET]

    # Tender Register kolon indeksleri (1-indexed), sekme basligina gore sabit:
    # Tender ID, Company, Portal, Tender Ref, Tender Date, Status, Product Segment,
    # Product Description, Qty, UOM, Winner, Brand, Total INR Basic, GST INR,
    # Total INR Incl GST, FX INR/EUR, Total EUR, Unit EUR Basic, Unit EUR Incl GST,
    # Source URL, PDF Saved?, Notes
    URL_COL = 20
    ID_COL = 1

    existing_urls = _existing_urls(ws_reg, URL_COL, TENDER_REGISTER_HEADER_ROW)

    new_register_rows = 0
    new_price_rows = 0

    for lead in leads:
        if lead.url in existing_urls:
            continue  # zaten kayitli, tekrar ekleme

        tender_id = _next_tender_id(ws_reg, ID_COL, TENDER_REGISTER_HEADER_ROW)
        info = extracted_by_url.get(lead.url)

        status = "New Lead" if not info else ("Docs Found" if info.tender_ref else "New Lead")

        row_values = [
            tender_id,
            lead.portal_name,
            lead.portal_name,  # Portal kolonu (kaynagi ayni deger ile doldur)
            info.tender_ref if info else None,
            None,  # Tender Date - PDF'den otomatik cikarilmiyor (v1)
            status,
            lead.matched_keyword or "",
            lead.title,
            info.qty if info else None,
            info.unit if info else None,
            info.winner if info else "Not found",
            "Unknown",
            info.total_price_inr if info else None,
            None,  # GST INR - manuel/hesaplanacak
            None,  # Total INR Incl GST
            None,  # FX INR/EUR - Price Intelligence sekmesinde merkezi tutulur
            None,
            None,
            None,
            lead.url,
            "Yes" if (info and info.text_excerpt) else "No",
            f"Bot tarafindan tespit edildi ({datetime.now():%Y-%m-%d})",
        ]
        ws_reg.append(row_values)
        existing_urls.add(lead.url)
        new_register_rows += 1

        # Fiyat/miktar cikarilabildiyse Price Intelligence'a da ekle
        if info and (info.total_price_inr or info.qty):
            price_row = [
                tender_id,
                lead.portal_name,
                datetime.now().year,
                lead.matched_keyword or "",
                None,  # Capacity - manuel
                info.qty,
                info.winner or "Not found",
                "Unknown",
                info.total_price_inr,
                None,  # Total EUR Basic - FX ile hesaplanacak (main.py'de)
                None,
                None,
                info.confidence,
                lead.url,
                "Bot tarafindan tespit edildi, dogrulama gerekli",
            ]
            ws_price.append(price_row)
            new_price_rows += 1

    # Source Log'a ozet satir ekle
    ws_log.append([
        f"{datetime.now():%Y-%m-%d %H:%M}",
        f"Otomatik tarama: {new_register_rows} yeni ihale, {new_price_rows} yeni fiyat kaydi",
        "bot",
    ])

    wb.save(workbook_path)
    logger.info("Workbook guncellendi: %s yeni ihale, %s yeni fiyat kaydi",
                new_register_rows, new_price_rows)

    return {"new_register_rows": new_register_rows, "new_price_rows": new_price_rows}
