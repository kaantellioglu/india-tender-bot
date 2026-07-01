"""Write/update tender intelligence workbook."""
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
TENDER_REGISTER_HEADER_ROW = 3
PRICE_INTEL_HEADER_ROW = 3


def _existing_url_map(ws, url_col_idx: int, header_row: int) -> dict[str, int]:
    urls: dict[str, int] = {}
    for r_idx in range(header_row + 1, ws.max_row + 1):
        val = ws.cell(r_idx, url_col_idx).value
        if val:
            urls[str(val).strip()] = r_idx
    return urls


def _next_tender_id(ws, id_col_idx: int, header_row: int, prefix: str = "T-") -> str:
    max_num = 0
    for row in ws.iter_rows(min_row=header_row + 1, max_col=id_col_idx, values_only=True):
        val = row[id_col_idx - 1]
        if val and str(val).startswith(prefix):
            try:
                max_num = max(max_num, int(str(val).replace(prefix, "")))
            except ValueError:
                continue
    return f"{prefix}{max_num + 1:04d}"


def _is_empty(v) -> bool:
    return v is None or str(v).strip() in {"", "—", "Unknown", "Not found", "None"}


def _set_if_empty(ws, row: int, col: int, value) -> bool:
    if value is None or value == "":
        return False
    if _is_empty(ws.cell(row, col).value):
        ws.cell(row, col).value = value
        return True
    return False


def _meta_note(lead: TenderLead, info: ExtractedTenderInfo | None = None) -> str:
    extra = lead.extra or {}
    score = extra.get("lead_score") or (info.lead_score if info else "")
    priority = extra.get("priority") or (info.priority if info else "")
    source_type = extra.get("source_type") or (info.source_type if info else lead.file_type)
    closing = extra.get("closing_date") or (info.closing_date if info else "")
    equip = extra.get("equipment_segment") or (info.equipment_segment if info else "")
    reasons = ",".join(extra.get("score_reasons") or [])[:200]
    return f"Bot tespit/zenginlestirme ({datetime.now():%Y-%m-%d}); meta:score={score};priority={priority};source_type={source_type};closing_date={closing};equipment={equip};reasons={reasons}"


def _lead_values(tender_id: str, lead: TenderLead, info: ExtractedTenderInfo | None) -> list:
    extra = lead.extra or {}
    tender_ref = (info.tender_ref if info else None) or extra.get("tender_ref")
    tender_date = (info.tender_date if info else None) or extra.get("tender_date") or lead.published_date
    closing_date = (info.closing_date if info else None) or extra.get("closing_date")
    segment = (info.equipment_segment if info else None) or extra.get("equipment_segment") or lead.matched_keyword or ""
    desc = (info.product_description if info else None) or lead.raw_snippet or lead.title
    qty = info.qty if info else None
    unit = info.unit if info else None
    winner = info.winner if info else None
    price = info.total_price_inr if info else None
    status = "Awarded / Result" if winner or any(x in (lead.title or "").lower() for x in ["loa", "foa", "aoc", "award"]) else ("Docs Found" if tender_ref else "New Lead")
    note = _meta_note(lead, info)
    if closing_date:
        note += f"; next_action=check_closing_date:{closing_date}"
    return [
        tender_id,
        lead.portal_name,
        lead.portal_name,
        tender_ref,
        tender_date,
        status,
        segment,
        desc[:1000] if isinstance(desc, str) else desc,
        qty,
        unit,
        winner or "Not found",
        "Unknown",
        price,
        None,
        None,
        None,
        None,
        None,
        None,
        lead.url,
        "Yes" if (info and info.text_excerpt) else ("HTML" if lead.file_type == "html" else "No"),
        note,
    ]


def update_workbook(workbook_path: str | Path, leads: Iterable[TenderLead], extracted_by_url: dict[str, ExtractedTenderInfo]) -> dict:
    workbook_path = Path(workbook_path)
    wb = openpyxl.load_workbook(workbook_path)
    ws_reg = wb[TENDER_REGISTER_SHEET]
    ws_price = wb[PRICE_INTEL_SHEET]
    ws_log = wb[SOURCE_LOG_SHEET]

    URL_COL = 20
    ID_COL = 1
    existing_urls = _existing_url_map(ws_reg, URL_COL, TENDER_REGISTER_HEADER_ROW)
    new_register_rows = 0
    new_price_rows = 0
    enriched_rows = 0

    for lead in leads:
        info = extracted_by_url.get(lead.url)
        if lead.url in existing_urls:
            row = existing_urls[lead.url]
            changed = False
            changed |= _set_if_empty(ws_reg, row, 4, (info.tender_ref if info else None) or lead.extra.get("tender_ref"))
            changed |= _set_if_empty(ws_reg, row, 5, (info.tender_date if info else None) or lead.extra.get("tender_date") or lead.published_date)
            changed |= _set_if_empty(ws_reg, row, 7, (info.equipment_segment if info else None) or lead.extra.get("equipment_segment") or lead.matched_keyword)
            changed |= _set_if_empty(ws_reg, row, 8, (info.product_description if info else None) or lead.raw_snippet or lead.title)
            changed |= _set_if_empty(ws_reg, row, 9, info.qty if info else None)
            changed |= _set_if_empty(ws_reg, row, 10, info.unit if info else None)
            changed |= _set_if_empty(ws_reg, row, 11, info.winner if info else None)
            changed |= _set_if_empty(ws_reg, row, 13, info.total_price_inr if info else None)
            old_note = ws_reg.cell(row, 22).value or ""
            meta = _meta_note(lead, info)
            if "meta:score=" not in str(old_note):
                ws_reg.cell(row, 22).value = f"{old_note}; {meta}" if old_note else meta
                changed = True
            if changed:
                enriched_rows += 1
            continue

        tender_id = _next_tender_id(ws_reg, ID_COL, TENDER_REGISTER_HEADER_ROW)
        row_values = _lead_values(tender_id, lead, info)
        ws_reg.append(row_values)
        existing_urls[lead.url] = ws_reg.max_row
        new_register_rows += 1

        if info and (info.total_price_inr or info.qty or info.winner):
            ws_price.append([
                tender_id,
                lead.portal_name,
                datetime.now().year,
                info.equipment_segment or lead.extra.get("equipment_segment") or lead.matched_keyword or "",
                None,
                info.qty,
                info.winner or "Not found",
                "Unknown",
                info.total_price_inr,
                None,
                None,
                None,
                info.confidence,
                lead.url,
                _meta_note(lead, info),
            ])
            new_price_rows += 1

    ws_log.append([
        f"{datetime.now():%Y-%m-%d %H:%M}",
        f"Otomatik tarama: {new_register_rows} yeni ihale, {new_price_rows} yeni fiyat kaydi, {enriched_rows} satir zenginlestirildi",
        "bot",
    ])

    wb.save(workbook_path)
    logger.info("Workbook guncellendi: %s yeni ihale, %s yeni fiyat kaydi, %s zenginlestirme", new_register_rows, new_price_rows, enriched_rows)
    return {"new_register_rows": new_register_rows, "new_price_rows": new_price_rows, "enriched_rows": enriched_rows}
