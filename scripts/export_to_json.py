"""
data/India_Procurement_Intelligence_Database.xlsx dosyasini okuyup
docs/data.json uretir. GitHub Pages'teki dashboard (docs/index.html) bu
JSON'u fetch() ile okur - xlsx dosyasi tarayicida dogrudan acilmaz, bu yuzden
her bot calismasindan sonra bu script calistirilir (bkz. .github/workflows).

Kullanim:
    python -m scripts.export_to_json
    python scripts/export_to_json.py --workbook data/....xlsx --out docs/data.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = ROOT / "data" / "India_Procurement_Intelligence_Database.xlsx"
DEFAULT_OUT = ROOT / "docs" / "data.json"


def rows_as_dicts(ws, header_row: int, headers: list[str]) -> list[dict]:
    out = []
    for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row, values_only=True):
        if row is None or all(v is None for v in row):
            continue
        # ilk kolon (ID/isim) bos ise satiri atla - bos ayirici satirlar var
        if row[0] is None:
            continue
        record = {}
        for h, v in zip(headers, row):
            if isinstance(v, datetime):
                v = v.strftime("%Y-%m-%d")
            record[h] = v
        out.append(record)
    return out


def export(workbook_path: Path, out_path: Path) -> None:
    wb = openpyxl.load_workbook(workbook_path, data_only=True)

    # --- 01 Portal Master ---
    ws = wb["01 Portal Master"]
    portal_headers = [
        "tier", "name", "type", "website", "tender_search_url", "award_url",
        "login_requirement", "relevance", "note", "next_action",
    ]
    portals = rows_as_dicts(ws, header_row=3, headers=portal_headers)

    # --- 04 Tender Register ---
    ws = wb["04 Tender Register"]
    tender_headers = [
        "tender_id", "company", "portal", "tender_ref", "tender_date", "status",
        "product_segment", "product_description", "qty", "uom", "winner",
        "brand", "total_inr_basic", "gst_inr", "total_inr_incl_gst", "fx_inr_eur",
        "total_eur", "unit_eur_basic", "unit_eur_incl_gst", "source_url",
        "pdf_saved", "notes",
    ]
    tenders = rows_as_dicts(ws, header_row=3, headers=tender_headers)

    # --- 06 Price Intelligence ---
    ws = wb["06 Price Intelligence"]
    price_headers = [
        "tender_id", "company", "year", "product_segment", "capacity", "qty",
        "winner", "brand", "total_inr_basic", "total_eur_basic", "unit_eur_basic",
        "unit_eur_incl_gst", "confidence", "source_url", "notes",
    ]
    price_intel = rows_as_dicts(ws, header_row=3, headers=price_headers)

    # --- 07 Competitor DB ---
    ws = wb["07 Competitor DB"]
    comp_headers = ["name", "country", "role", "segment", "website", "relevance", "notes"]
    competitors = rows_as_dicts(ws, header_row=3, headers=comp_headers)

    # --- 08 Source Log (son 50 kayit) ---
    ws = wb["08 Source Log"]
    log_headers = ["timestamp", "message", "actor"]
    source_log = rows_as_dicts(ws, header_row=3, headers=log_headers)[-50:]

    dashboard = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "portal_count": len(portals),
        "tender_count": len(tenders),
        "price_row_count": len(price_intel),
        "competitor_count": len(competitors),
        "awarded_count": sum(1 for t in tenders if (t.get("status") or "").lower() == "awarded"),
        "high_relevance_portals": sum(1 for p in portals if (p.get("relevance") or "").lower() == "high"),
        "tier1_count": sum(1 for p in portals if p.get("tier") == "Tier 1"),
        "tier2_count": sum(1 for p in portals if p.get("tier") == "Tier 2"),
        "tier3_count": sum(1 for p in portals if p.get("tier") == "Tier 3"),
    }

    payload = {
        "dashboard": dashboard,
        "portals": portals,
        "tenders": tenders,
        "price_intelligence": price_intel,
        "competitors": competitors,
        "source_log": source_log,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Yazildi: {out_path} "
          f"({len(portals)} portal, {len(tenders)} ihale, {len(price_intel)} fiyat kaydi)")


def parse_args():
    parser = argparse.ArgumentParser(description="xlsx -> docs/data.json")
    parser.add_argument("--workbook", type=str, default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export(Path(args.workbook), Path(args.out))
