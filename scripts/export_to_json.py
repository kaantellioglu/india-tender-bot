"""
data/India_Procurement_Intelligence_Database.xlsx dosyasini okuyup
docs/data.json uretir.

v2 iyilestirmeleri:
- Dashboard icin veri kalitesi metrikleri eklenir.
- Portal bazli durum/eksik veri ozetleri eklenir.
- Tablodaki hyperlink hucreleri varsa URL degeri korunur.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = ROOT / "data" / "India_Procurement_Intelligence_Database.xlsx"
DEFAULT_OUT = ROOT / "docs" / "data.json"


def _serialise(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    return v


def rows_as_dicts(ws, header_row: int, headers: list[str]) -> list[dict]:
    out = []
    for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row):
        values = [cell.value for cell in row]
        if not values or all(v is None for v in values):
            continue
        if values[0] is None:
            continue

        record = {}
        for idx, h in enumerate(headers):
            cell = row[idx] if idx < len(row) else None
            value = cell.value if cell is not None else None
            if cell is not None and cell.hyperlink and not value:
                value = cell.hyperlink.target
            record[h] = _serialise(value)
        out.append(record)
    return out


def _blank(v: Any) -> bool:
    return v is None or str(v).strip() == "" or str(v).strip().lower() in {"unknown", "not found", "—", "none"}


def _source_type(url: str | None) -> str:
    if not url:
        return "unknown"
    low = str(url).lower().split("?")[0]
    if low.endswith(".pdf"):
        return "pdf"
    if low.endswith((".doc", ".docx")):
        return "doc"
    if low.endswith((".xls", ".xlsx")):
        return "excel"
    if low.endswith(".zip"):
        return "zip"
    return "html"


def _is_high_value(row: dict) -> bool:
    hay = " ".join(str(row.get(k) or "") for k in [
        "product_segment", "product_description", "notes", "tender_ref"
    ]).lower()
    hints = [
        "service regulator", "commercial regulator", "industrial regulator",
        "rms", "mrs", "drs", "frs", "prs", "cgs", "metering skid",
        "regulator skid", "gas train", "slam shut", "ssv", "relief valve",
    ]
    return any(h in hay for h in hints)


def _quality_flags(row: dict) -> list[str]:
    flags = []
    if _blank(row.get("tender_ref")):
        flags.append("missing_ref")
    if _blank(row.get("tender_date")):
        flags.append("missing_date")
    if _blank(row.get("qty")):
        flags.append("missing_qty")
    if _blank(row.get("winner")) or str(row.get("winner")).lower() == "not found":
        flags.append("missing_winner")
    if _blank(row.get("total_inr_basic")) and _blank(row.get("unit_eur_basic")) and _blank(row.get("unit_eur_incl_gst")):
        flags.append("missing_price")
    return flags


def _enrich_tenders(tenders: list[dict]) -> list[dict]:
    for row in tenders:
        row["source_type"] = _source_type(row.get("source_url"))
        row["high_value"] = _is_high_value(row)
        row["quality_flags"] = _quality_flags(row)
        row["quality_score"] = max(0, 100 - len(row["quality_flags"]) * 18)
    return tenders


def _portal_health(tenders: list[dict]) -> list[dict]:
    bucket = defaultdict(list)
    for t in tenders:
        bucket[t.get("company") or t.get("portal") or "Unknown"].append(t)

    health = []
    for portal, rows in sorted(bucket.items()):
        total = len(rows)
        pdf = sum(1 for r in rows if r.get("source_type") == "pdf")
        high = sum(1 for r in rows if r.get("high_value"))
        with_ref = sum(1 for r in rows if not _blank(r.get("tender_ref")))
        with_qty = sum(1 for r in rows if not _blank(r.get("qty")))
        with_price = sum(1 for r in rows if not (
            _blank(r.get("total_inr_basic")) and _blank(r.get("unit_eur_basic")) and _blank(r.get("unit_eur_incl_gst"))
        ))
        avg_quality = round(sum(r.get("quality_score", 0) for r in rows) / total, 1) if total else 0
        health.append({
            "portal": portal,
            "total": total,
            "pdf": pdf,
            "high_value": high,
            "with_ref": with_ref,
            "with_qty": with_qty,
            "with_price": with_price,
            "avg_quality": avg_quality,
        })
    return sorted(health, key=lambda r: (r["high_value"], r["total"]), reverse=True)


def export(workbook_path: Path, out_path: Path) -> None:
    wb = openpyxl.load_workbook(workbook_path, data_only=True)

    ws = wb["01 Portal Master"]
    portal_headers = [
        "tier", "name", "type", "website", "tender_search_url", "award_url",
        "login_requirement", "relevance", "note", "next_action",
    ]
    portals = rows_as_dicts(ws, header_row=3, headers=portal_headers)

    ws = wb["04 Tender Register"]
    tender_headers = [
        "tender_id", "company", "portal", "tender_ref", "tender_date", "status",
        "product_segment", "product_description", "qty", "uom", "winner",
        "brand", "total_inr_basic", "gst_inr", "total_inr_incl_gst", "fx_inr_eur",
        "total_eur", "unit_eur_basic", "unit_eur_incl_gst", "source_url",
        "pdf_saved", "notes",
    ]
    tenders = _enrich_tenders(rows_as_dicts(ws, header_row=3, headers=tender_headers))

    ws = wb["06 Price Intelligence"]
    price_headers = [
        "tender_id", "company", "year", "product_segment", "capacity", "qty",
        "winner", "brand", "total_inr_basic", "total_eur_basic", "unit_eur_basic",
        "unit_eur_incl_gst", "confidence", "source_url", "notes",
    ]
    price_intel = rows_as_dicts(ws, header_row=3, headers=price_headers)

    ws = wb["07 Competitor DB"]
    comp_headers = ["name", "country", "role", "segment", "website", "relevance", "notes"]
    competitors = rows_as_dicts(ws, header_row=3, headers=comp_headers)

    ws = wb["08 Source Log"]
    log_headers = ["timestamp", "message", "actor"]
    source_log = rows_as_dicts(ws, header_row=3, headers=log_headers)[-80:]

    status_counts = dict(Counter((t.get("status") or "Unknown") for t in tenders))
    source_type_counts = dict(Counter((t.get("source_type") or "unknown") for t in tenders))
    missing_core_fields = {
        "tender_ref": sum(1 for t in tenders if _blank(t.get("tender_ref"))),
        "tender_date": sum(1 for t in tenders if _blank(t.get("tender_date"))),
        "qty": sum(1 for t in tenders if _blank(t.get("qty"))),
        "winner": sum(1 for t in tenders if _blank(t.get("winner")) or str(t.get("winner")).lower() == "not found"),
        "price": sum(1 for t in tenders if (
            _blank(t.get("total_inr_basic")) and _blank(t.get("unit_eur_basic")) and _blank(t.get("unit_eur_incl_gst"))
        )),
    }

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
        "high_value_count": sum(1 for t in tenders if t.get("high_value")),
        "pdf_count": sum(1 for t in tenders if t.get("source_type") == "pdf"),
        "avg_quality": round(sum(t.get("quality_score", 0) for t in tenders) / len(tenders), 1) if tenders else 0,
        "missing_core_fields": missing_core_fields,
        "status_counts": status_counts,
        "source_type_counts": source_type_counts,
    }

    payload = {
        "dashboard": dashboard,
        "portals": portals,
        "tenders": tenders,
        "price_intelligence": price_intel,
        "competitors": competitors,
        "source_log": source_log,
        "portal_health": _portal_health(tenders),
        "status_counts": status_counts,
        "source_type_counts": source_type_counts,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"Yazildi: {out_path} "
        f"({len(portals)} portal, {len(tenders)} ihale, {len(price_intel)} fiyat kaydi)"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="xlsx -> docs/data.json")
    parser.add_argument("--workbook", type=str, default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export(Path(args.workbook), Path(args.out))
