"""Write/update tender intelligence workbook with clean market-target gates."""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable
import openpyxl
from ..scrapers.base_scraper import TenderLead
from ..parsers.pdf_parser import ExtractedTenderInfo
from ..quality.market_filter import classify_market_record
logger = logging.getLogger(__name__)
TENDER_REGISTER_SHEET="04 Tender Register"; PRICE_INTEL_SHEET="06 Price Intelligence"; SOURCE_LOG_SHEET="08 Source Log"; TENDER_REGISTER_HEADER_ROW=3

def _existing_url_map(ws, url_col_idx:int, header_row:int):
    return {str(ws.cell(r,url_col_idx).value).strip():r for r in range(header_row+1, ws.max_row+1) if ws.cell(r,url_col_idx).value}

def _next_tender_id(ws, id_col_idx:int, header_row:int, prefix="T-"):
    max_num=0
    for row in ws.iter_rows(min_row=header_row+1, max_col=id_col_idx, values_only=True):
        val=row[id_col_idx-1]
        if val and str(val).startswith(prefix):
            try: max_num=max(max_num, int(str(val).replace(prefix,"")))
            except ValueError: pass
    return f"{prefix}{max_num+1:04d}"

def _is_empty(v): return v is None or str(v).strip() in {"","—","Unknown","Not found","None"}
def _set_if_empty(ws,row,col,value):
    if value is None or value=="": return False
    if _is_empty(ws.cell(row,col).value): ws.cell(row,col).value=value; return True
    return False

def _combined_text(lead, info=None): return " ".join(str(x or "") for x in [lead.title, lead.raw_snippet, lead.matched_keyword, lead.url, lead.extra.get("row_text"), lead.extra.get("equipment_segment"), info.product_description if info else "", info.equipment_segment if info else ""])
def _quality_for(lead, info=None):
    if info and info.quality_status:
        return {"quality_status":info.quality_status,"market_relevance":info.market_relevance,"equipment_segment":info.equipment_segment,"document_type":info.document_type,"matched_terms":info.target_terms,"reject_reasons":info.reject_reasons,"confidence":info.confidence}
    return classify_market_record(_combined_text(lead, info), equipment_relevance=lead.extra.get("equipment_relevance"), source_url=lead.url).to_dict()
def _should_store(lead, info=None):
    q=_quality_for(lead,info)
    if q.get("quality_status")=="market_target": return True
    if q.get("quality_status")=="needs_review": return bool((info and (info.tender_ref or info.qty or info.total_price_inr or info.winner)) or lead.extra.get("tender_ref"))
    return False

def _meta_note(lead, info=None):
    extra=lead.extra or {}; q=_quality_for(lead, info); unit_price=getattr(info,"unit_price_inr",None) if info else None; amount_label=getattr(info,"amount_label","") if info else ""
    return (f"Bot clean extraction ({datetime.now():%Y-%m-%d}); meta:score={extra.get('lead_score') or (info.lead_score if info else '')};priority={extra.get('priority') or (info.priority if info else '')};"
            f"source_type={extra.get('source_type') or (info.source_type if info else lead.file_type)};closing_date={extra.get('closing_date') or (info.closing_date if info else '')};"
            f"equipment={q.get('equipment_segment','')};quality_status={q.get('quality_status','')};market_relevance={q.get('market_relevance','')};document_type={q.get('document_type','')};"
            f"unit_price_inr={unit_price or ''};amount_label={amount_label};matched_terms={','.join(q.get('matched_terms') or [])[:180]};reject_reasons={','.join(q.get('reject_reasons') or [])[:180]};"
            "scope=market_intelligence_only;excluded_scope=no_bid_or_offer_submission_automation")

def _lead_values(tender_id, lead, info):
    q=_quality_for(lead,info); extra=lead.extra or {}; desc=(info.product_description if info else None) or lead.raw_snippet or lead.title
    doc_type=q.get("document_type"); winner=info.winner if info else None
    status="Awarded / Result" if winner or doc_type in {"award","loa","foa","po_work_order"} else ("Docs Found" if ((info.tender_ref if info else None) or extra.get("tender_ref")) else "New Lead")
    return [tender_id,lead.portal_name,lead.portal_name,(info.tender_ref if info else None) or extra.get("tender_ref"),(info.tender_date if info else None) or extra.get("tender_date") or lead.published_date,status,q.get("equipment_segment") or extra.get("equipment_segment") or lead.matched_keyword or "",desc[:1000] if isinstance(desc,str) else desc,info.qty if info else None,info.unit if info else None,winner or "Not found","Unknown",info.total_price_inr if info else None,None,None,None,None,getattr(info,"unit_price_inr",None) if info else None,getattr(info,"unit_price_inr",None) if info else None,lead.url,"Yes" if (info and info.text_excerpt) else ("HTML" if lead.file_type=="html" else "No"),_meta_note(lead,info)]

def update_workbook(workbook_path: str|Path, leads: Iterable[TenderLead], extracted_by_url: dict[str, ExtractedTenderInfo]) -> dict:
    workbook_path=Path(workbook_path); wb=openpyxl.load_workbook(workbook_path); ws_reg=wb[TENDER_REGISTER_SHEET]; ws_price=wb[PRICE_INTEL_SHEET]; ws_log=wb[SOURCE_LOG_SHEET]
    existing_urls=_existing_url_map(ws_reg,20,TENDER_REGISTER_HEADER_ROW); new_register_rows=new_price_rows=enriched_rows=skipped_non_target=0
    for lead in leads:
        info=extracted_by_url.get(lead.url)
        if not _should_store(lead,info): skipped_non_target+=1; continue
        if lead.url in existing_urls:
            row=existing_urls[lead.url]; changed=False; q=_quality_for(lead,info)
            changed|=_set_if_empty(ws_reg,row,4,(info.tender_ref if info else None) or lead.extra.get("tender_ref")); changed|=_set_if_empty(ws_reg,row,5,(info.tender_date if info else None) or lead.extra.get("tender_date") or lead.published_date)
            changed|=_set_if_empty(ws_reg,row,7,q.get("equipment_segment") or lead.extra.get("equipment_segment") or lead.matched_keyword); changed|=_set_if_empty(ws_reg,row,8,(info.product_description if info else None) or lead.raw_snippet or lead.title)
            changed|=_set_if_empty(ws_reg,row,9,info.qty if info else None); changed|=_set_if_empty(ws_reg,row,10,info.unit if info else None); changed|=_set_if_empty(ws_reg,row,11,info.winner if info else None); changed|=_set_if_empty(ws_reg,row,13,info.total_price_inr if info else None); changed|=_set_if_empty(ws_reg,row,18,getattr(info,"unit_price_inr",None) if info else None); changed|=_set_if_empty(ws_reg,row,19,getattr(info,"unit_price_inr",None) if info else None)
            old_note=ws_reg.cell(row,22).value or ""; meta=_meta_note(lead,info)
            if "quality_status=" not in str(old_note): ws_reg.cell(row,22).value=f"{old_note}; {meta}" if old_note else meta; changed=True
            if changed: enriched_rows+=1
            continue
        tender_id=_next_tender_id(ws_reg,1,TENDER_REGISTER_HEADER_ROW); ws_reg.append(_lead_values(tender_id,lead,info)); existing_urls[lead.url]=ws_reg.max_row; new_register_rows+=1
        q=_quality_for(lead,info); has_commercial=info and (info.total_price_inr or info.qty or info.winner or getattr(info,"unit_price_inr",None))
        if info and q.get("quality_status")=="market_target" and has_commercial:
            ws_price.append([tender_id,lead.portal_name,datetime.now().year,q.get("equipment_segment") or lead.extra.get("equipment_segment") or lead.matched_keyword or "",None,info.qty,info.winner or "Not found","Unknown",info.total_price_inr,None,getattr(info,"unit_price_inr",None),getattr(info,"unit_price_inr",None),info.confidence,lead.url,_meta_note(lead,info)]); new_price_rows+=1
    ws_log.append([f"{datetime.now():%Y-%m-%d %H:%M}",f"Clean tarama: {new_register_rows} yeni ihale, {new_price_rows} yeni fiyat kaydi, {enriched_rows} zenginlestirme, {skipped_non_target} non-target atlandi","bot"])
    wb.save(workbook_path); logger.info("Workbook guncellendi: %s yeni ihale, %s yeni fiyat kaydi, %s zenginlestirme, %s non-target atlandi",new_register_rows,new_price_rows,enriched_rows,skipped_non_target)
    return {"new_register_rows":new_register_rows,"new_price_rows":new_price_rows,"enriched_rows":enriched_rows,"skipped_non_target":skipped_non_target}
