# Küresel gaz dağıtımı ve ihale kaynakları

İlk sürüm, 249 ISO 3166-1 ülke ve bölge kodu için kapsam takibi, 22 pazarda 192 operatör kaydı ve 17 operatörle eşlenmiş 20 ihale veya tedarik kanalı içeriyor.

| Dosya | İçerik |
|---|---|
| countries.csv | Ülke ve bölge bazında araştırma durumu ve başlangıç kaynağı |
| operators.csv | Dağıtım operatörü, kuruluşu doğrulayan kaynak ve kayıt anahtarı |
| procurement_sources.csv | Operatör anahtarı, kanal türü, bağlantı, eşleştirme kanıtı ve otomatik tarama durumu |

Kapsam şehir veya bölge düzeyinde boru hattıyla doğal gaz dağıtımıdır. Sadece iletim, depolama, gaz satışı veya LPG yapan şirketler bu kapsamın dışındadır. Birden fazla faaliyet yürüten şirketler için dağıtım kanıtı aranır. Türkiye’de EPDK iletişim listesindeki adlar kısa biçimde tutuluyor. Kayıtlar lisansların güncel durumunu ayrıca teyit etmeyi gerektirebilir. Hindistan başlangıç listesi PNGRB’nin iki yayınına dayanıyor. Avrupa’daki bazı kayıtlar ACER’in gaz DSO üyelik ekinden geliyor. Ülke bazında tam kapsama ayrıca doğrulanmalıdır.

`araştırma bekliyor` durumunda kapsama ilişkin karar verilmemiştir. Bir şirketin tedarikçi portalı, herkese açık ihale listesi ve tekil ihale belgesi farklı kanal türleri olarak kaydedilir. Bağlantının listelenmesi otomatik taramanın başarılı olduğu anlamına gelmez.

Eklemeleri önce operatör kaydına, ardından aynı `operatör_id` ile kanal tablosuna girin. Ülke tablosundaki sayıları güncelleyin. Anahtar ve bağlantı değişikliklerinde operatörün kimliğini resmî kaynakla kontrol edin.

[ISO ülke ve bölge kodları](https://www.iso.org/iso-3166-country-codes.html)
