"""
Generic scraper: login/DSC gerektirmeyen, acik HTML ihale listesi sayfalari icin.

v2 iyilestirmeleri:
- Sadece <a> text/href degil, linkin bulundugu tablo satiri (<tr>) veya liste/kart
  konteyneri de okunur. Bu sayede tender no, tarih, closing date ve aciklama
  bilgileri daha iyi yakalanir.
- Portal basina limit ortam degiskeniyle ayarlanabilir:
      MAX_LEADS_PER_PORTAL=120
- Her lead.extra icine ham satir metni, tahmini tender_ref, tender_date,
  closing_date ve source_type bilgileri yazilir.
- LOA/AOC/FOA gibi sonuc belgeleri "awarded_candidate" olarak isaretlenir.
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urljoin, urldefrag

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, TenderLead

logger = logging.getLogger(__name__)

STRONG_DOCUMENT_HINTS = [
    "nit", "rfq", "rfp", "eoi", "corrigendum", "aoc", "loa", "foa", "boq",
    "tender no", "tender ref", "tender_no", "bid no", "e-tender", "award",
    "letter of award", "contract award", "purchase order", "po no",
]

# Dar kapsamli ekipman kelimeleri. Bunlar generic "tender/procurement" yerine
# gaz ekipmani odakli signal uretir.
GAS_EQUIPMENT_HINTS = [
    "regulator", "governor", "pressure reducing", "pressure reduction",
    "metering", "rms", "mrs", "drs", "frs", "prs", "cgs", "skid",
    "slam shut", "ssv", "relief valve", "gas train", "png", "cng",
]

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")
DEFAULT_MAX_LEADS_PER_PORTAL = 120

DATE_RE = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}"
    r")\b",
    re.IGNORECASE,
)

TENDER_REF_RE = re.compile(
    r"\b("
    r"(?:tender|bid|rfq|rfp|eoi|nit|loa|foa|aoc|po)\s*(?:no\.?|ref\.?|number)?\s*[:#-]?\s*[A-Z0-9][A-Z0-9/_\-.]{3,}|"
    r"[A-Z]{2,12}/[A-Z0-9][A-Z0-9/_\-.]{4,}"
    r")\b",
    re.IGNORECASE,
)

CLOSING_HINT_RE = re.compile(r"(closing|last date|due date|bid end|submission|end date)", re.IGNORECASE)


def _clean_text(text: str | None, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]


def _normalise_url(url: str) -> str:
    return urldefrag(url.strip())[0]


def _is_document(url: str) -> bool:
    return url.lower().split("?")[0].endswith(DOC_EXTENSIONS)


def _file_type(url: str) -> str:
    path = url.lower().split("?")[0]
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith((".doc", ".docx")):
        return "doc"
    if path.endswith((".xls", ".xlsx")):
        return "excel"
    if path.endswith(".zip"):
        return "zip"
    return "html"


def _best_container_text(a) -> str:
    """Linkin icinde oldugu tablo satiri/liste/kart metnini dondurur."""
    container = a.find_parent("tr")
    if container is None:
        container = a.find_parent(["li", "article", "div"])
    link_text = a.get_text(" ", strip=True) or ""
    if container is None:
        return _clean_text(link_text)
    row_text = container.get_text(" ", strip=True)
    # Bazı nav div'leri cok uzun olabilir; link text'i de koru.
    if len(row_text) > 900:
        row_text = link_text
    return _clean_text(row_text or link_text)


def _extract_first_date(text: str) -> str | None:
    m = DATE_RE.search(text or "")
    return m.group(1).strip() if m else None


def _extract_closing_date(text: str) -> str | None:
    if not text:
        return None
    # Closing/due kelimesinden sonraki 160 karakterde tarih ara.
    for m in CLOSING_HINT_RE.finditer(text):
        chunk = text[m.start(): m.start() + 160]
        dm = DATE_RE.search(chunk)
        if dm:
            return dm.group(1).strip()
    return None


def _extract_tender_ref(text: str) -> str | None:
    m = TENDER_REF_RE.search(text or "")
    if not m:
        return None
    value = _clean_text(m.group(1), limit=120)
    # Aşırı genel yakalamaları azalt.
    if len(value) < 5:
        return None
    return value


def _score_candidate(*, matched_kw: str | None, strong_doc_hint: bool, equipment_hint: bool,
                     is_doc: bool, row_text: str, url: str) -> int:
    score = 0
    if matched_kw:
        score += 100
    if strong_doc_hint:
        score += 80
    if equipment_hint:
        score += 60
    if is_doc:
        score += 25
    low = f"{row_text} {url}".lower()
    if any(x in low for x in ("aoc", "loa", "foa", "award", "successful bidder")):
        score += 35
    if any(x in low for x in ("corrigendum", "amendment")):
        score += 10
    if _extract_tender_ref(row_text):
        score += 20
    if _extract_first_date(row_text):
        score += 10
    return score


class GenericScraper(BaseScraper):
    def fetch_leads(self) -> list[TenderLead]:
        candidates: list[tuple[int, TenderLead]] = []
        url = self.portal.get("tender_search_url") or self.portal.get("website")
        if not url:
            return []

        resp = self._get(url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        seen_urls: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith("javascript:") or href.startswith("#") or href.lower().startswith("mailto:"):
                continue

            full_url = _normalise_url(urljoin(url, href))
            if full_url in seen_urls:
                continue

            link_text = a.get_text(" ", strip=True) or ""
            row_text = _best_container_text(a)
            haystack = f"{link_text} {href} {row_text}".lower()

            is_doc = _is_document(full_url)
            matched_kw = self._matches_keyword(haystack)
            strong_doc_hint = is_doc and any(h in haystack for h in STRONG_DOCUMENT_HINTS)
            equipment_hint = any(h in haystack for h in GAS_EQUIPMENT_HINTS)

            # Kabul mantigi:
            # 1) Keyword eslesmesi, 2) guclu belge sinyali, 3) dokuman + gaz ekipmani
            # 4) tablo satirinda tender/closing + gaz ekipmani birlikte geciyorsa.
            tender_context = ("tender" in haystack or "bid" in haystack or "rfq" in haystack or "nit" in haystack)
            if not (matched_kw or strong_doc_hint or (is_doc and equipment_hint) or (tender_context and equipment_hint)):
                continue

            seen_urls.add(full_url)
            tender_ref = _extract_tender_ref(row_text) or _extract_tender_ref(link_text) or _extract_tender_ref(href)
            tender_date = _extract_first_date(row_text)
            closing_date = _extract_closing_date(row_text)
            awarded_candidate = any(x in haystack for x in ("aoc", "loa", "foa", "award", "successful bidder"))

            title = _clean_text(row_text or link_text or full_url, limit=260)
            score = _score_candidate(
                matched_kw=matched_kw,
                strong_doc_hint=strong_doc_hint,
                equipment_hint=equipment_hint,
                is_doc=is_doc,
                row_text=row_text,
                url=full_url,
            )

            lead = TenderLead(
                portal_id=self.portal["id"],
                portal_name=self.portal["name"],
                title=title,
                url=full_url,
                matched_keyword=matched_kw,
                published_date=tender_date,
                file_type=_file_type(full_url),
                raw_snippet=row_text,
                extra={
                    "tender_ref": tender_ref,
                    "tender_date": tender_date,
                    "closing_date": closing_date,
                    "source_type": _file_type(full_url),
                    "awarded_candidate": awarded_candidate,
                    "score": score,
                    "row_text": row_text,
                },
            )
            candidates.append((score, lead))

        candidates.sort(key=lambda item: item[0], reverse=True)

        try:
            max_leads = int(os.getenv("MAX_LEADS_PER_PORTAL", str(DEFAULT_MAX_LEADS_PER_PORTAL)))
        except ValueError:
            max_leads = DEFAULT_MAX_LEADS_PER_PORTAL

        leads = [lead for _, lead in candidates[:max_leads]]

        if len(candidates) > max_leads:
            logger.info(
                "%s: %d aday bulundu, ilk %d tanesi alindi (limit)",
                self.portal["name"], len(candidates), max_leads,
            )
        else:
            logger.info("%s: %d aday link bulundu", self.portal["name"], len(leads))

        return leads
