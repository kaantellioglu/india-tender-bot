# V3.2 Source Cleanup & Archive Discovery

Bu patch, V4 Award / Price Engine öncesinde kaynakları temizlemek ve her portal için doğru veri erişim stratejisini belirlemek için hazırlandı.

## Sabit kapsam

Botun amacı yalnızca **market intelligence** toplamaktır:

- 2023’ten bugüne açılmış gaz regülatörü, RMS, MRS, DRS, PRS, gas filter station, skid, gas train ve ilgili gaz ekipmanı ihaleleri
- aktif ihaleler
- geçmiş ihale sonuçları
- AOC / LOA / FOA / award / work order kayıtları
- kazanan firma ve rakip bilgisi
- miktar, toplam tutar, birim fiyat
- yıllara ve bölgelere göre hedef fiyat analizi

Kapsam dışı:

- portal üzerinde işlem yapmak
- korunan portal adımlarını otomatikleştirmek
- ticari/procurement transaction oluşturmak
- CAPTCHA/DSC gibi korunan mekanizmaları otomatik geçmek

## Yeni dosyalar

```text
config/source_cleanup.yaml
src/discovery/__init__.py
src/discovery/archive_discovery.py
README_PATCH_v32.md
```

## Güncellenen ana davranış

- `generic_scraper.py` artık tek bir URL yerine portal için tanımlanan birden fazla public source URL’yi tarar.
- `portal_rules.yaml` içine public tender, archive ve award URL’leri eklendi.
- `source_cleanup.yaml` dashboard’a “hangi portal için ne düzeltilecek?” panosu verir.
- Login/Access Review dili market intelligence kapsamına çekildi.
- Dashboard’a `Source Cleanup` sekmesi eklendi.
- `Portal Health` içinde public tender URL ve archive/award URL görünür.

## V4’e geçmeden önce hedef

Aşağıdaki kaynaklar temizlendikten sonra V4 Award / Price Engine için ilk kaynak grubu olacak:

1. GAIL AOC / LOA / FOA archive
2. IGL tender/detail pages
3. Gasonet public tender PDFs
4. MNGL active/archive pages
5. Vadodara Gas URL repair + historical PDFs
6. CPPP/eProcure public search results

## Kurulum

```cmd
git pull --rebase origin main
```

ZIP içindeki dosyaları repo köküne kopyalayın.

```cmd
git status
git add .
git commit -m "V3.2 source cleanup ve archive discovery eklendi"
git pull --rebase origin main
git push
```

Sonra GitHub Actions’tan workflow’u çalıştırın.
