"""
Tum portal scraper'larinin miras alacagi temel sinif.

Her scraper, bir portal sayfasini (veya birden fazla sayfayi) tarar ve
bulunan ihale/duyuru linklerini TenderLead listesi olarak dondurur.
Gercek indirme/parse islemi ayri modullerde (parsers/) yapilir.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ESKA-TenderBot/1.0"
    )
}


@dataclass
class TenderLead:
    """Bir portalda bulunan tek bir ihale/duyuru adayi."""

    portal_id: str
    portal_name: str
    title: str
    url: str
    matched_keyword: Optional[str] = None
    published_date: Optional[str] = None
    file_type: Optional[str] = None  # "pdf", "html", vb.
    raw_snippet: Optional[str] = None
    extra: dict = field(default_factory=dict)


class BaseScraper:
    """Tum scraper siniflarinin temel arayuzu."""

    def __init__(self, portal: dict, keywords: List[dict], timeout: int = 20,
                 request_delay: float = 1.5):
        self.portal = portal
        self.keywords = [k["keyword"] for k in keywords]
        self.timeout = timeout
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    # --- Alt siniflarin override etmesi gereken metod ---
    def fetch_leads(self) -> List[TenderLead]:
        raise NotImplementedError

    # --- Ortak yardimcilar ---
    def _get(self, url: str) -> Optional[requests.Response]:
        try:
            resp = self.session.get(url, timeout=self.timeout)
            time.sleep(self.request_delay)  # portali yormamak icin nazik gecikme
            if resp.status_code == 200:
                return resp
            logger.warning("HTTP %s -> %s", resp.status_code, url)
        except requests.RequestException as exc:
            logger.warning("Istek basarisiz: %s (%s)", url, exc)
        return None

    def _matches_keyword(self, text: str) -> Optional[str]:
        text_low = (text or "").lower()
        for kw in self.keywords:
            if kw.lower() in text_low:
                return kw
        return None
