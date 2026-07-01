"""
CPPP (Central Public Procurement Portal - etenders.gov.in) icin ozel scraper.

CPPP, sonuclari bir arama formu (organizasyon + anahtar kelime) ile dondurur
ve cogu zaman sunucu taraflarinda oturum/csrf token ister; ayrica "Latest
Active Tenders" disindaki (Archive) kayitlar genelde JavaScript ile render
edilir. Bu yuzden GenericScraper burada yeterli olmuyor.

Bu dosya, ileride Playwright/Selenium ile tamamlanabilecek bir iskelet
sunar: `search()` metodu, her organizasyon x her anahtar kelime kombinasyonu
icin CPPP'nin "Search Tender" REST/AJAX uc noktasina istek atacak sekilde
genisletilebilir.

Su an icin: portal.yaml'da CPPP scraper='generic' olarak birakildi, cunku
JS-render sayfalarda GenericScraper bos donebilir. Bu dosya, gelistirmeye
hazir bir baslangic noktasi olarak duruyor ve main.py tarafindan
scraper == 'cppp' olarak isaretlenen portallar icin cagrilabilir.
"""
from __future__ import annotations

import logging

from .base_scraper import BaseScraper, TenderLead

logger = logging.getLogger(__name__)

# CPPP'de taranmasi istenen kurum/organizasyon isimleri (Portal Master'daki
# "03 How To Search" sayfasindan alindi)
CPPP_ORGANISATIONS = [
    "GAIL (India) Limited",
    "GAIL Gas Limited",
    "Maharashtra Natural Gas Limited",
    "Indian Oil Corporation Limited",
    "Bharat Petroleum Corporation Limited",
    "Hindustan Petroleum Corporation Limited",
    "Engineers India Limited",
    "MECON Limited",
]


class CPPPScraper(BaseScraper):
    """
    NOT (TODO - genisletme noktasi):
    CPPP'nin arama sonucu HTML'i JS ile doldugu icin `requests` + BeautifulSoup
    tek basina yetmez. Onerilen yol:

        pip install playwright
        playwright install chromium

    ve `fetch_leads` icinde:
      1. Playwright ile sayfayi ac
      2. "Organisation Name" alanina CPPP_ORGANISATIONS listesinden birini yaz
      3. Her config/keywords.yaml anahtar kelimesini "Search Tender" kutusuna yaz
      4. Sonuc tablosundaki satirlari TenderLead'e cevir

    Bu bilincli olarak stub birakildi; CPPP'ye otomatik, yuksek siklikli
    istek atmak sunucu tarafinda IP engeline yol acabilir - production'a
    almadan once portalin kullanim sartlarini/robots.txt'ini kontrol edin.
    """

    def fetch_leads(self) -> list[TenderLead]:
        logger.info(
            "%s: CPPP scraper henuz tam otomatik degil (JS render). "
            "Manuel kontrol icin dogrudan link: %s",
            self.portal["name"],
            self.portal.get("tender_search_url"),
        )
        return []
