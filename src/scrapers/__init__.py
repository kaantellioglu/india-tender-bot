from .base_scraper import BaseScraper, TenderLead
from .generic_scraper import GenericScraper
from .cppp_scraper import CPPPScraper

SCRAPER_REGISTRY = {
    "generic": GenericScraper,
    "cppp": CPPPScraper,
}


def get_scraper(portal: dict, keywords: list[dict]) -> BaseScraper:
    """portal['scraper'] alanina gore uygun scraper sinifini dondurur."""
    scraper_cls = SCRAPER_REGISTRY.get(portal.get("scraper", "generic"), GenericScraper)
    return scraper_cls(portal, keywords)


__all__ = ["BaseScraper", "TenderLead", "GenericScraper", "CPPPScraper",
           "SCRAPER_REGISTRY", "get_scraper"]
