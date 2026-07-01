"""
Generic scraper: login/DSC gerektirmeyen, acik HTML ihale listesi sayfalari icin.

Calisma mantigi:
1. portal['tender_search_url'] sayfasini indir
2. Sayfadaki tum <a> linklerini tara
3. Bir link ancak asagidaki durumlarda "aday" sayilir:
   a) Link metni/href, config/keywords.yaml'daki SPESIFIK anahtar kelimelerden
      biriyle eslesirse (orn. "domestic regulator", "service regulator") -> her
      dosya turunde kabul edilir; bu kelimeler zaten dar/spesifik oldugu icin
      site menusundeki genel linklerle karismaz.
   b) Link bir PDF/DOC ise VE dosya adinda/metninde LOA/AOC/FOA/NIT/Corrigendum
      gibi GERCEK BELGE isaretlerinden biri geciyorsa -> kabul edilir.
   Salt "tender", "bid", "procurement", "regulator" gibi tek basina genel
   kelimeler ARTIK yeterli degil - bu kelimeler site navigasyon menulerinde
   ("Regulatory Compliance", "About Procurement" vb.) de gectigi icin ciddi
   yanlis-pozitif ("gurultu") uretiyordu (bkz. ilk test kosusunda IGL'de 1611,
   Vadodara'da 258 sahte aday bulunmasi).
4. Portal basina cikan aday sayisi MAX_LEADS_PER_PORTAL ile sinirlanir; en
   guclu sinyalli (spesifik anahtar kelime eslesenler) once alinir.

Bu scraper JavaScript render gerektiren (SPA) portallarda calismaz; bu
portallar icin ayrica bir Playwright tabanli scraper eklenebilir
(bkz. README "Genisletme" bolumu).
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, TenderLead

logger = logging.getLogger(__name__)

# Sadece gercek ihale/ihale-sonucu BELGELERINDE gecen, site menusunde
# rastlanma ihtimali dusuk, dar kapsamli isaretler. Bunlar tek basina (PDF/DOC
# uzantili linklerle birlikte) bir adayi tetikleyebilir.
STRONG_DOCUMENT_HINTS = [
    "nit", "rfq", "rfp", "eoi", "corrigendum", "aoc", "loa", "foa", "boq",
    "tender no", "tender ref", "tender_no", "bid no", "e-tender",
]

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx")

MAX_LEADS_PER_PORTAL = 40


class GenericScraper(BaseScraper):
    def fetch_leads(self) -> list[TenderLead]:
        candidates: list[TenderLead] = []
        url = self.portal.get("tender_search_url") or self.portal.get("website")
        if not url:
            return candidates

        resp = self._get(url)
        if resp is None:
            return candidates

        soup = BeautifulSoup(resp.text, "html.parser")
        seen_urls: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True) or ""
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue

            full_url = urljoin(url, href)
            if full_url in seen_urls:
                continue

            haystack = f"{text} {href}".lower()
            is_document = full_url.lower().split("?")[0].endswith(DOC_EXTENSIONS)

            matched_kw = self._matches_keyword(haystack)
            strong_doc_hint = is_document and any(h in haystack for h in STRONG_DOCUMENT_HINTS)

            if not (matched_kw or strong_doc_hint):
                continue

            seen_urls.add(full_url)
            file_type = "pdf" if full_url.lower().split("?")[0].endswith(".pdf") else (
                "doc" if is_document else "html"
            )

            candidates.append(
                TenderLead(
                    portal_id=self.portal["id"],
                    portal_name=self.portal["name"],
                    title=text or full_url,
                    url=full_url,
                    matched_keyword=matched_kw,
                    file_type=file_type,
                    raw_snippet=text,
                )
            )

        # Spesifik anahtar-kelime eslesenleri one al (daha guvenilir sinyal),
        # sonra portal basina makul bir tavan uygula.
        candidates.sort(key=lambda l: 0 if l.matched_keyword else 1)
        leads = candidates[:MAX_LEADS_PER_PORTAL]

        if len(candidates) > MAX_LEADS_PER_PORTAL:
            logger.info(
                "%s: %d aday bulundu, ilk %d tanesi alindi (limit)",
                self.portal["name"], len(candidates), MAX_LEADS_PER_PORTAL,
            )
        else:
            logger.info("%s: %d aday link bulundu", self.portal["name"], len(leads))

        return leads