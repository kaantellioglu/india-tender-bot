"""Generate an India pilot review report without external model calls."""
import argparse
import json
from collections import Counter
from pathlib import Path

from scripts.india_agents import ROOT, SOURCES


def present(value):
    return str(value or "—").replace("|", "¦").replace("\r", " ").replace("\n", " ")


def report(payload):
    stats = payload["dashboard"]
    tenders = payload["tenders"]
    prices = payload["price_intelligence"]
    portals = payload["portals"]
    actions = [row for row in payload["access_queue"] if row.get("status", "open") == "open"]
    channels = [row for row in portals if row.get("tender_search_url") or row.get("award_url")]
    winners = [row for row in tenders if not row.get("missing_winner") and row.get("winner")]
    lines = [
        "# Hindistan ihale pilotu",
        "",
        f"Dönem başlangıcı {stats['archive_start']} · {stats['lookback_months']} ay",
        f"Veri tarihi {stats['generated_at']}",
        "",
        "## 1. Ülke ihale sistemi",
        "",
        *[f"- {source['id'].upper()} · {source['url']}" for source in SOURCES],
        "",
        "## 2. Operatör ve satın alma kaynakları",
        "",
        f"Portal envanterinde {len(portals)} kayıt ve satın alma ya da sonuç bağlantısı bulunan {len(channels)} kayıt var.",
        "",
        "| Kurum | İhale kanalı | Sonuç kanalı |",
        "|---|---|---|",
        *["| " + " | ".join(present(row.get(key)) for key in ("name", "tender_search_url", "award_url")) + " |" for row in channels],
        "",
        "## 3. Portal erişimi ve kayıt",
        "",
        f"Açık inceleme kayıtları {len(actions)}.",
        "",
        *[f"- {present(kind)} · {count}" for kind, count in Counter(row.get("action_type") for row in actions).most_common()],
        "",
        "## 4. İhale sonuçları ve fiyat adayları",
        "",
        f"Dönem içi ihale {len(tenders)} · Kazanan alanı dolu ihale {len(winners)} · Eşleşen fiyat satırı {len(prices)}.",
        "",
        "| İhale | Firma | Birim fiyat (EUR, vergi hariç) | Güven | Kaynak |",
        "|---|---|---|---|---|",
        *["| " + " | ".join(present(row.get(key)) for key in ("tender_id", "winner", "unit_eur_basic", "confidence", "source_url")) + " |" for row in prices],
        "",
        "Fiyat satırları Excel arşivinden gelir. Kazanan ve birim fiyat, orijinal sonuç belgesiyle karşılaştırılarak onaylanmalıdır.",
        "",
        "## 5. Denetim ve sonraki ülke testi",
        "",
        f"- İlan tarihi doğrulanamayan kayıtlar · {stats['undated_count']}",
        f"- Miktarı eksik dönem içi kayıtlar · {sum(bool(row.get('missing_qty')) for row in tenders)}",
        "- İkinci ülke testi · Sonuç belgesindeki ihale referansı ve kalemi eşleştir. Karma lot toplamını birim fiyat olarak kabul etme.",
        "- Bu rapor Excel verisinden kurallarla üretilmiştir. Model çağrısı ve portal işlemi yapılmamıştır.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "docs/data.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
