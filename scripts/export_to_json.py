"""Export Excel + diagnostic queues to docs/data.json for GitHub Pages.

Scope: market intelligence only. No bid/offer submission workflow is exported.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = ROOT / "data" / "India_Procurement_Intelligence_Database.xlsx"
DEFAULT_OUT = ROOT / "docs" / "data.json"
FAILURES_PATH = ROOT / "data" / "source_failures.json"
ACTIONS_PATH = ROOT / "data" / "action_queue.json"


def rows_as_dicts(ws, header_row: int, headers: list[str]) -> list[dict]:
    out = []
    for row in ws.iter_rows(min_row=header_row + 1, max_row=ws.max_row, values_only=True):
        if row is None or all(v is None for v in row):
            continue
        if row[0] is None:
            continue
        record = {}
        for h, v in zip(headers, row):
            if isinstance(v, datetime):
                v = v.strftime("%Y-%m-%d")
            record[h] = v
        out.append(record)
    return out


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def parse_meta(notes: str | None) -> dict:
    notes = str(notes or "")
    meta = {}
    m = re.search(r"meta:(.*)", notes)
    if not m:
        return meta
    for part in m.group(1).split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta


def safe_int(v, default=0):
    try:
        if v in (None, ""):
            return default
        return int(float(str(v)))
    except Exception:
        return default


def derive_tender_fields(t: dict) -> dict:
    meta = parse_meta(t.get("notes"))
    t["lead_score"] = safe_int(meta.get("score"), 0)
    t["priority"] = meta.get("priority") or ("High" if t["lead_score"] >= 70 else "Medium" if t["lead_score"] >= 40 else "Low")
    t["source_type"] = meta.get("source_type") or ("pdf" if str(t.get("source_url") or "").lower().split("?")[0].endswith(".pdf") else "html")
    t["closing_date"] = meta.get("closing_date") or ""
    t["equipment"] = meta.get("equipment") or t.get("product_segment") or ""
    t["missing_ref"] = not bool(t.get("tender_ref"))
    t["missing_date"] = not bool(t.get("tender_date"))
    t["missing_qty"] = not bool(t.get("qty"))
    t["missing_winner"] = not bool(t.get("winner")) or str(t.get("winner")).lower() in {"not found", "unknown", "none"}
    t["missing_price"] = not bool(t.get("total_inr_basic")) and not bool(t.get("unit_eur_basic")) and not bool(t.get("unit_eur_incl_gst"))
    return t


def build_portal_health(portals: list[dict], tenders: list[dict], failures: list[dict], actions: list[dict]) -> list[dict]:
    by_portal_tenders = Counter(t.get("company") or t.get("portal") or "" for t in tenders)
    by_portal_failures = defaultdict(list)
    by_portal_actions = defaultdict(list)
    for f in failures:
        by_portal_failures[f.get("portal") or f.get("portal_id")].append(f)
    for a in actions:
        by_portal_actions[a.get("portal") or a.get("portal_id")].append(a)

    health = []
    for p in portals:
        name = p.get("name") or ""
        fl = by_portal_failures.get(name, []) + by_portal_failures.get(p.get("id"), [])
        ac = by_portal_actions.get(name, []) + by_portal_actions.get(p.get("id"), [])
        status = "OK"
        if any((f.get("failure_type") or "").startswith("http_403") or f.get("failure_type") in {"credentials_required", "protected_manual_review"} for f in fl) or ac:
            status = "Access Review"
        elif any(f.get("failure_type") in {"dns_error", "ssl_error", "timeout", "connection_refused", "redirect_loop"} for f in fl):
            status = "Access Problem"
        elif any((f.get("failure_type") or "").startswith("http_404") for f in fl):
            status = "Broken URL"
        elif fl:
            status = "Review"
        health.append({
            "portal": name,
            "portal_id": p.get("id", ""),
            "tier": p.get("tier", ""),
            "relevance": p.get("relevance", ""),
            "status": status,
            "lead_count": by_portal_tenders.get(name, 0),
            "failure_count": len(fl),
            "open_access_review_count": len([x for x in ac if x.get("status", "open") == "open"]),
            "top_failure": Counter(f.get("failure_type") for f in fl).most_common(1)[0][0] if fl else "",
            "next_action": (ac[-1].get("next_action") if ac else p.get("next_action", "")),
            "website": p.get("website", ""),
        })
    return health


def export(workbook_path: Path, out_path: Path) -> None:
    wb = openpyxl.load_workbook(workbook_path, data_only=True)

    ws = wb["01 Portal Master"]
    portal_headers = ["tier", "name", "type", "website", "tender_search_url", "award_url", "login_requirement", "relevance", "note", "next_action"]
    portals = rows_as_dicts(ws, 3, portal_headers)

    ws = wb["04 Tender Register"]
    tender_headers = ["tender_id", "company", "portal", "tender_ref", "tender_date", "status", "product_segment", "product_description", "qty", "uom", "winner", "brand", "total_inr_basic", "gst_inr", "total_inr_incl_gst", "fx_inr_eur", "total_eur", "unit_eur_basic", "unit_eur_incl_gst", "source_url", "pdf_saved", "notes"]
    tenders = [derive_tender_fields(t) for t in rows_as_dicts(ws, 3, tender_headers)]

    ws = wb["06 Price Intelligence"]
    price_headers = ["tender_id", "company", "year", "product_segment", "capacity", "qty", "winner", "brand", "total_inr_basic", "total_eur_basic", "unit_eur_basic", "unit_eur_incl_gst", "confidence", "source_url", "notes"]
    price_intel = rows_as_dicts(ws, 3, price_headers)

    ws = wb["07 Competitor DB"]
    comp_headers = ["name", "country", "role", "segment", "website", "relevance", "notes"]
    competitors = rows_as_dicts(ws, 3, comp_headers)

    ws = wb["08 Source Log"]
    log_headers = ["timestamp", "message", "actor"]
    source_log = rows_as_dicts(ws, 3, log_headers)[-100:]

    failures = load_json_list(FAILURES_PATH)
    actions = load_json_list(ACTIONS_PATH)
    portal_health = build_portal_health(portals, tenders, failures, actions)

    dashboard = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "portal_count": len(portals),
        "tender_count": len(tenders),
        "price_row_count": len(price_intel),
        "competitor_count": len(competitors),
        "awarded_count": sum(1 for t in tenders if "award" in str(t.get("status") or "").lower()),
        "high_priority_count": sum(1 for t in tenders if t.get("priority") == "High"),
        "medium_priority_count": sum(1 for t in tenders if t.get("priority") == "Medium"),
        "failure_count": len(failures),
        "open_access_review_count": len([a for a in actions if a.get("status", "open") == "open"]),
        "portal_access_review_count": sum(1 for p in portal_health if p.get("status") in {"Access Review", "Access Problem", "Broken URL"}),
        "missing_ref_count": sum(1 for t in tenders if t.get("missing_ref")),
        "missing_date_count": sum(1 for t in tenders if t.get("missing_date")),
        "missing_qty_count": sum(1 for t in tenders if t.get("missing_qty")),
        "missing_price_count": sum(1 for t in tenders if t.get("missing_price")),
    }

    payload = {
        "dashboard": dashboard,
        "portals": portals,
        "tenders": tenders,
        "price_intelligence": price_intel,
        "competitors": competitors,
        "source_log": source_log,
        "source_failures": failures[-1000:],
        "action_queue": actions[-1000:],
        "access_queue": actions[-1000:],
        "portal_health": portal_health,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Yazildi: {out_path} ({len(portals)} portal, {len(tenders)} ihale, {len(price_intel)} fiyat, {len(failures)} failure, {len(actions)} access-review)")


def parse_args():
    parser = argparse.ArgumentParser(description="xlsx + diagnostics -> docs/data.json")
    parser.add_argument("--workbook", type=str, default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    export(Path(args.workbook), Path(args.out))
