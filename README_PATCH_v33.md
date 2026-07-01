# V3.3 Clean Dataset & Commercial Extraction Patch

Bu patch dashboard'u genel ihale link listesinden çıkarıp temiz bir gas equipment market intelligence dataset haline getirir.

## Amaç

- Teklif verme / bid submission / DSC / CAPTCHA / EMD otomasyonu yok.
- Sadece 2023'ten bugüne gaz regülatörü, RMS, MRS, PRS, DRS, CGS, gas train, skid, gas filter station, safety valve gibi hedef ürün ihaleleri.
- PDF/HTML dokümanından adet, kazanan, toplam INR, birim INR ve doküman tipi çıkarımı.
- Alakasız kayıtlar dashboard clean dataset'ten çıkarılır.

## Yeni dosyalar

- `src/quality/market_filter.py`
- `src/parsers/commercial_extractor.py`

## Güncellenen ana dosyalar

- `src/parsers/pdf_parser.py`
- `src/scoring/lead_score.py`
- `src/classifiers/gas_equipment_classifier.py`
- `src/scrapers/generic_scraper.py`
- `src/storage/excel_store.py`
- `scripts/export_to_json.py`
- `.github/workflows/daily_scan.yml`

## Kurulum

```cmd
git pull --rebase origin main
```

ZIP içeriğini repo klasörüne kopyala.

```cmd
git add .
git commit -m "V3.3 clean dataset ve commercial extraction eklendi"
git pull --rebase origin main
git push
```

Sonra GitHub Actions > Daily Tender Scan > Run workflow.

Workflow validate kısmında artık şunları görmelisin:

- clean_tender_count
- raw_tender_count
- review_tender_count
- rejected_tender_count
- price_row_count
