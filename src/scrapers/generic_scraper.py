"""
Generic scraper: login/DSC gerektirmeyen, acik HTML ihale listesi sayfalari icin.

Calisma mantigi:
1. portal['tender_search_url'] sayfasini indir
2. Sayfadaki tum <a> linklerini tara
3. Link metni veya href, config/keywords.yaml'daki anahtar kelimelerden
   biriyle eslesirse -> TenderLead olustur
4. PDF uzantili linkleri ayrica isaretle (fiyat/teknik detay icin sonradan
   parsers/pdf_parser.py ile indirilip okunacak)

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

# Genel ihale sayfalarinda link metninde sikca gecen, ihale/duyuru olduguna
# isaret eden genel-amacli terimler (Turkce dahil, portallarin cogu Ingilizce)
GENERIC_TENDER_HINTS = [
    "tender", "nit", "rfq", "rfp", "eoi", "corrigendum", "aoc", "loa", "foa",
    "boq", "bid", "purchase order", "regulator", "procurement",
]


class GenericScraper(BaseScraper):
    def fetch_leads(self) -> list[TenderLead]:
        leads: list[TenderLead] = []
        url = self.portal.get("tender_search_url") or self.portal.get("website")
        if not url:
            return leads

        resp = self._get(url)
        if resp is None:
            return leads

        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True) or ""
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue

            full_url = urljoin(url, href)
            haystack = f"{text} {href}"

            matched_kw = self._matches_keyword(haystack)
            generic_hint = any(h in haystack.lower() for h in GENERIC_TENDER_HINTS)

            if not (matched_kw or generic_hint):
                continue

            file_type = "pdf" if full_url.lower().endswith(".pdf") else "html"

            leads.append(
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

        logger.info("%s: %d aday link bulundu", self.portal["name"], len(leads))
        return leads
