# V3.1 Access Resolution Patch - Market Intelligence Only

Bu patch, V3'te oluşan `Login & Actions` mantığını ESKA'nın gerçek amacıyla hizalar:

- Bot teklif vermez.
- Bot bid/proposal submission yapmaz.
- Bot DSC imzalama, CAPTCHA bypass, EMD/tender fee ödeme veya portal üzerinde işlem yapma akışı oluşturmaz.
- Botun görevi: 2023 ve sonrası gas regulator, RMS, MRS, PRS, gas filter/station/skid vb. ihaleleri ve sonuçlarını izlemek; kazananları, rakipleri, miktarları, toplam tutarları ve birim fiyatları analiz etmektir.

## Değişen yaklaşım

Eski V3 terimleri:

- Login & Actions
- manual action
- bid/login/DSC aksiyonu gibi algılanabilecek metinler

Yeni V3.1 terimleri:

- Access Review
- public market-intelligence extraction
- credential-protected document access review
- vendor registration / empanelment status check
- protected manual review
- excluded scope: no bid or offer submission automation

## Dashboard değişiklikleri

- `Login & Actions` sekmesi `Access Review` olarak değiştirildi.
- `Open Actions` metriği `Access Reviews` oldu.
- Access Review tablosuna şu alanlar eklendi:
  - Access Type
  - Data Access
  - Requirement
  - Data Automation Scope
  - Technical Action
  - Business Check
  - Excluded Scope

## Kod değişiklikleri

- `src/access/login_detector.py`
  - Login sinyalleri artık teklif verme aksiyonu olarak değil, veri erişim sınırlaması olarak sınıflandırılır.
- `src/diagnostics/source_failure.py`
  - Her action/failure kaydı `market_intelligence_only` kapsamıyla işaretlenir.
  - Her kayda `excluded_scope = no_bid_or_offer_submission_automation` eklenir.
- `docs/index.html`
  - Dashboard wording market intelligence amacına göre düzeltildi.
- `scripts/export_to_json.py`
  - `access_queue` alias'ı eklendi.
  - Portal Health artık `Access Review` terimini kullanır.

## Sonraki faz

V3.1'den sonra V4 şu alanlara odaklanmalıdır:

- Award / AOC / LOA / FOA sonuç arşivi taraması
- BOQ ve price schedule tablo extraction
- Kazanan firma / rakip / adet / toplam bedel / birim fiyat çıkarımı
- Yıllara göre hedef fiyat ve rakip fiyat analizi

