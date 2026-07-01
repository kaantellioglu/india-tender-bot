# ESKA India Tender Bot

`India_Procurement_Intelligence_Database.xlsx` dosyasindaki mantigi (51 portal,
24 anahtar kelime, rakip listesi) otomatiklestiren bir tarama botu. Her
calistirmada Hindistan'daki gaz/CGD ihale portallarini dolasir, anahtar
kelimelerle eslesen yeni ihale/ihale-sonucu (AOC/LOA/FOA) belgelerini bulur,
bulabildigi PDF'lerden fiyat/miktar/kazanan bilgisini cikarir ve **ayni
Excel dosyasina** (ayni sekme/kolon yapisiyla) ekler.

## Neler yapiyor, neler yapmiyor

**Yapiyor:**
- `config/portals.yaml` (51 portal), `config/keywords.yaml` (24 kelime) ve
  `config/competitors.yaml` (11 rakip) — hepsi orijinal xlsx'ten uretildi.
- Login/DSC gerektirmeyen, acik HTML sayfalarini tarar (GenericScraper).
- Bulunan PDF linklerini indirip regex tabanli fiyat/miktar/ihale no/kazanan
  cikarimi dener (`src/parsers/pdf_parser.py`).
- Sonuclari `04 Tender Register` ve `06 Price Intelligence` sekmelerine,
  URL bazinda tekrar kontrolu yaparak ekler.
- Yeni kayit bulundugunda e-posta / Telegram bildirimi atar (opsiyonel).
- GitHub Actions ile her gun otomatik calisir ve guncellenen xlsx'i repoya
  commitler.

**Yapmiyor / sinirlari (onemli, gercekci olmak icin):**
- **DSC/login gerektiren portallar** (MGL, MNGL, GGL/nProcure, CPPP bid
  gonderimi vb.) otomatik tarama disidir — bunlar icin sadece "manuel kontrol
  linki" saglanir. Bot sizin adiniza teklif vermez/sisteme giris yapmaz.
- **JavaScript ile render olan (SPA) sayfalar** (CPPP arama sonucu gibi)
  GenericScraper ile bos donebilir. `src/scrapers/cppp_scraper.py` icinde
  Playwright ile nasil genisletilecegi anlatildi, ama v1'de aktif degil.
  Bu bilincli bir karar: CPPP'ye otomatik/sik istek atmak IP engeline yol
  acabilir, once portalin kullanim sartlari kontrol edilmeli.
  Anthropic/Claude bu asamada CPPP icin otomatik bir bypass yazmadi.
- PDF'ler cok farkli formatlarda oldugundan fiyat/miktar cikarimi
  **"best effort"** dur; `Confidence: Low/Medium/High` etiketiyle isaretlenir,
  Low/Medium olanlar mutlaka goz ile dogrulanmali.
- Rakip fiyatlarini "bulmak", pratikte rakip firmalarin kazandigi ihalelerin
  AOC/LOA belgelerini taramak anlamina gelir (bu zaten `07 Competitor DB` +
  `04 Tender Register` mantigi). Bot rakiplerin kendi fiyat listelerini veya
  gizli tekliflerini bulamaz — sadece kamuya acik ihale sonuc belgelerini.

## Kurulum

```bash
git clone <bu-repo>
cd india-tender-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`data/India_Procurement_Intelligence_Database.xlsx` repoya dahil edildi (sizin
yuklediginiz dosyanin bir kopyasi) — bot bunun uzerine yeni satirlar ekler.

## Calistirma

```bash
# Tum portallari tara
python -m src.main

# Sadece Tier 1 portallari tara (daha hizli, gunluk test icin)
python -m src.main --tiers "Tier 1"

# Farkli bir xlsx dosyasi uzerinde calis
python -m src.main --workbook data/India_Procurement_Intelligence_Database.xlsx
```

Calistirinca konsolda hangi portalda kac aday link bulundugunu, kac PDF
analiz edildigini ve kac yeni satir eklendigini gorursunuz.

## Otomatik (GitHub Actions) calistirma

`.github/workflows/daily_scan.yml` her gun 05:00 UTC'de calisir ve
degisiklik varsa xlsx'i otomatik commitler. Bildirim istiyorsaniz repo
**Settings > Secrets and variables > Actions** altinda su secret'lari
tanimlayin (hepsi opsiyonel, tanimlamazsaniz bildirim atlanir):

| Secret | Aciklama |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFY_EMAIL_TO` | E-posta bildirimi icin |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram bildirimi icin |

Lokal test icin `.env.example` dosyasini `.env` olarak kopyalayip
`python-dotenv` ile yukleyebilir ya da degiskenleri terminale export
edebilirsiniz.

## Proje yapisi

```
india-tender-bot/
├── config/
│   ├── portals.yaml        # 51 portal (Tier 1/2/3), Portal Master'dan uretildi
│   ├── keywords.yaml        # 24 arama anahtar kelimesi
│   └── competitors.yaml     # 11 rakip firma
├── src/
│   ├── scrapers/
│   │   ├── base_scraper.py  # Ortak arayuz (TenderLead, HTTP yardimcilari)
│   │   ├── generic_scraper.py  # Acik HTML sayfalari icin
│   │   └── cppp_scraper.py     # CPPP icin iskelet/TODO (JS render)
│   ├── parsers/
│   │   └── pdf_parser.py    # PDF'den fiyat/miktar/kazanan cikarimi
│   ├── storage/
│   │   └── excel_store.py   # Sonuclari xlsx'e yazar (tekrar kontrolu ile)
│   ├── notifier/
│   │   └── notify.py        # E-posta / Telegram bildirimi
│   ├── portal_loader.py     # config/*.yaml okuma
│   └── main.py               # Orkestratör (CLI giris noktasi)
├── data/
│   └── India_Procurement_Intelligence_Database.xlsx  # Uzerine yazilan ana dosya
└── .github/workflows/daily_scan.yml   # Gunluk otomatik calistirma
```

## Genisletme onerileri (sonraki adimlar)

1. **CPPP/nProcure/GeM icin Playwright scraper** — su an stub. En yuksek
   getiriyi bu portallar saglar cunku PSU/CGD ihalelerinin cogu buradan
   gecer.
2. **Tender Date cikarimi** — PDF parser'a tarih regex'i eklenebilir.
3. **Duplicate/normalizasyon** — ayni ihalenin birden fazla portalda
   (orn. hem sirket sitesi hem CPPP) gorunmesini birlestirme mantigi.
4. **FX (INR/EUR) otomatik guncelleme** — `06 Price Intelligence`
   sekmesindeki FX kolonu su an manuel; bir doviz API'si (orn. ECB) ile
   otomatiklestirebilirsiniz.
5. **Yeni portal eklemek** icin sadece `config/portals.yaml`'a satir eklemek
   yeterli; ozel bir scraper gerekiyorsa `scraper: cppp` gibi bir id verip
   `src/scrapers/__init__.py`'daki `SCRAPER_REGISTRY`'ye kaydedin.

## Yasal / etik not

Bu bot sadece herkese acik, login gerektirmeyen sayfalari tarar ve her
istek arasinda nazik bir gecikme (1.5 sn) birakir. Yine de production'a
almadan once her portalin `robots.txt` ve kullanim sartlarini kontrol
etmenizi, gerekiyorsa portal sahiplerinden izin almanizi oneririz.
