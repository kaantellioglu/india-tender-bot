# V3 Global Automation Core Patch

Bu paket Hindistan pilotunu global gas ekipmanları ihale takip ürününe çevirmek için temel otomasyon çekirdeğini ekler.

## Eklenen ana yetenekler

- PDF URL'si gerçek PDF mi kontrol edilir (`%PDF` magic check).
- PDF değilse HTML fallback ile sayfa içeriği işlenir.
- Sayfa üzerindeki tablo/kart satırları okunur; sadece link metniyle yetinilmez.
- Tender Ref, Tender Date, Closing Date, Quantity, Winner, INR amount gibi alanlar best-effort çıkarılır.
- Login / vendor registration / DSC / CAPTCHA sinyalleri ayrı `action_queue` olarak kaydedilir.
- 403, 404, DNS, SSL, timeout, redirect-loop, not-a-pdf gibi hatalar `source_failures` dosyasına yazılır.
- Gas equipment classifier eklendi: domestic regulator, service regulator, pressure regulator, PRS/DRS/MRS/RMS, skid, safety valve.
- Lead scoring eklendi: High / Medium / Low priority.
- Dashboard'a High Priority, Portal Health, Login & Actions, Failure Queue sekmeleri eklendi.
- Ülke bazlı yapı için `config/countries/india.yaml` eklendi.
- Portal öğrenme kuralları için `config/portal_rules.yaml` eklendi.

## Kurulum

Mevcut repo klasöründe:

```cmd
cd C:\Users\kaantellioglu\Downloads\india-tender-bot\india-tender-bot
git pull --rebase origin main
```

ZIP içeriğini bu klasörün üzerine kopyalayın. Sonra:

```cmd
git status
git add .
git commit -m "V3 global automation core eklendi"
git push
```

GitHub'da:

```text
Actions → Daily Tender Scan → Run workflow
```

## Beklenen dashboard sonuçları

- High Priority Leads dolacak.
- Failure Queue sekmesinde 403/404/DNS/SSL/not-a-pdf hataları görülecek.
- Login & Actions sekmesinde vendor login/DSC/CAPTCHA/manual action gerektiren kaynaklar görülecek.
- Portal Health sekmesi hangi portalın OK, Access Problem, Broken URL veya Action Required olduğunu gösterecek.

## Sonraki faz

V4'te Playwright tabanlı JS/form/login-aware scraper eklenmelidir. Bu, CPPP, TenderWizard, GeM, nProcure gibi portalları form üzerinden aramak için gereklidir.
