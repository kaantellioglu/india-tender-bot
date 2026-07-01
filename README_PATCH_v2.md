# India Tender Bot v2 Patch

Bu paket mevcut `india-tender-bot` repoya tek seferde kopyalanacak revize dosyaları içerir.

## İçerik

- `.github/workflows/daily_scan.yml`
  - Dashboard JSON üretimi devam eder.
  - Portal başına aday limiti 120'ye çıkarılır.
  - PDF parse limiti 120'ye çıkarılır.
  - `docs/data.json` doğrulaması genişletilir.

- `src/scrapers/generic_scraper.py`
  - Linkin bulunduğu tablo satırını/kartını da okur.
  - Tender ref, tarih, closing date, source type ve quality score çıkarır.
  - LOA/AOC/FOA/Award sinyallerini yakalar.
  - Portal başına limit `MAX_LEADS_PER_PORTAL` env değişkeniyle yönetilir.

- `src/parsers/pdf_parser.py`
  - PDF indirme koşulu düzeltildi.
  - PDF text + table extraction eklenir.
  - Ref, date, closing date, qty, winner, amount, product segment pattern'leri genişletilir.

- `src/storage/excel_store.py`
  - Eski URL'ler tamamen atlanmaz; boş alanlar varsa zenginleştirilir.
  - Yeni source log mesajı enrich sayısını da yazar.

- `scripts/export_to_json.py`
  - Dashboard kalite metrikleri, portal health, source type, quality flags eklenir.

- `docs/index.html`
  - Daha gelişmiş dashboard.
  - Portal, durum, kaynak tipi ve eksik veri filtreleri.
  - Ürün/ihale açıklaması görünür hale gelir.
  - Portal kalite sekmesi eklenir.

## Uygulama

1. Bu ZIP içeriğini mevcut proje klasörünün içine kopyala:

   `C:\Users\kaantellioglu\Downloads\india-tender-bot\india-tender-bot`

2. CMD:

```cmd
cd C:\Users\kaantellioglu\Downloads\india-tender-bot\india-tender-bot
git pull origin main --rebase
git add .
git commit -m "Scraper ve dashboard veri kalitesi iyilestirmeleri"
git push
```

3. GitHub Actions > Daily Tender Scan > Run workflow

4. İş bitince siteyi Ctrl+F5 ile yenile:

   `https://kaantellioglu.github.io/india-tender-bot/`

## Not

İlk çalıştırmada mevcut 2098 satırın sadece yeniden tespit edilen URL'leri zenginleşir. Her günlük taramada boş alanlar kademeli olarak dolar. Özellikle portal özel scraper'lar (GAIL/IGL/Gasonet) ileride eklenirse veri kalitesi daha da artar.
