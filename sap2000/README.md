# SAP2000 Profil Seçici

Bu araç SAP2000 modelinde tanımlı çubuk kesitlerini (profilleri) bir döngüyle tarar. Her adayı **hafiften ağıra** sırayla bir gruba atar ve koşulları kontrol eder. Koşulları sağlayan **en hafif** profili bulur.

Kontrol edilebilen koşullar:

| Koşul | Nasıl kontrol edilir | Analiz gerekir mi? |
|---|---|---|
| Ad deseni (`IPE*`, `HE*A` …) ve profil tipi | Süzgeç | Hayır |
| Geometrik sınırlar (alan, I33, W, Z, yükseklik …) | `PropFrame.GetSectProps` ve boyut fonksiyonları | Hayır |
| Çelik tasarım oranı ≤ sınır | `Analyze.RunAnalysis` → `DesignSteel.StartDesign` → `GetSummaryResults` | Evet |
| Maksimum deplasman ≤ sınır (mm) | `Results.JointDispl` | Evet |

Her aday için analiz yeniden çalıştırılır. Hiperstatik sistemlerde rijitlik değiştikçe kuvvetler yeniden dağılır, bu etki de sonuca yansır.

## Gereksinimler

- Windows, SAP2000 (v20 ve üzeri, OAPI etkin)
- Python 3.10 ve üzeri, `pip install comtypes`
- COM kaydı yoksa SAP2000 klasöründeki `RegisterSAP2000.exe` dosyasını yönetici olarak çalıştırın.

## Modelde hazırlık

1. Denenecek profiller modelde **tanımlı** olmalı. Örneğin *Define → Section Properties → Frame Sections → Import* ile IPE ve HEA serisini ekleyin. Araç yalnızca modeldeki kesitleri tarar.
2. Profili belirlenecek çubukları bir **gruba** alın (ör. `KIRISLER`).
3. Tasarım oranı kontrolü için çelik tasarım yönetmeliğini ve **tasarım kombinasyonlarını** tanımlayın (*Design → Steel Frame Design → Select Design Combos*).
4. Deplasman kontrolü yalnızca **düğüm noktalarındaki** deplasmanları okur. Kiriş ortası sehimi için kirişleri bölün ya da orta noktalara düğüm ekleyin. Bu noktaları bir gruba koyup `deplasman.grup` ile verin. Grup verilmezse ana gruptaki çubukların uç noktaları ve gruptaki noktalar kullanılır.
5. Modeli bir `.sdb` dosyasına kaydedin. Kaydedilmemiş model analiz edilemez.

## Kullanım

```bat
cd sap2000
pip install comtypes

:: Önce adayları ve geometrik uygunluğu gör (analiz yapmaz)
python -m profil_secici ornek_ayar.json --listele

:: Açık SAP2000 modeline bağlan, en hafif uygun profili bul (model değiştirilmez)
python -m profil_secici ornek_ayar.json

:: Bulunan profili gruba ata ve kaydet
python -m profil_secici ornek_ayar.json --uygula --kaydet

:: Tüm adayları değerlendirip CSV raporu al
python -m profil_secici ornek_ayar.json --mod tumu --rapor rapor.csv

:: Yeni SAP2000 örneği açıp belirli bir modeli kullan
python -m profil_secici ornek_ayar.json --yeni-ac C:\projeler\cati.sdb --gizli
```

Çıkış kodları: `0` profil bulundu, `1` SAP2000/çalışma hatası, `2` ayar hatası, `3` uygun profil yok.

`--uygula` verilmezse çalışma bitince (hata olsa bile) çubukların **özgün kesitleri geri yüklenir**. Analiz sonuçları ise silinmiş olur. `--uygula` ile seçilen profil grupta kalır ve model o profille analiz edilmiş durumda bırakılır.

## Ayar dosyası

```json
{
  "grup": "KIRISLER",
  "ad_desenleri": ["IPE*", "HE*A"],
  "profil_tipleri": ["I"],
  "geometrik": {
    "t3":  { "max": 40 },
    "i33": { "min": 2000 }
  },
  "tasarim":   { "oran_max": 0.95 },
  "deplasman": { "max_mm": 20, "yon": "U3", "kombinasyonlar": ["G+Q"], "grup": "KIRIS_ORTA_NOKTALAR" },
  "mod": "en_hafif",
  "uygula": false,
  "rapor": "profil_raporu.csv"
}
```

| Anahtar | Açıklama |
|---|---|
| `grup` | **Zorunlu.** Profilin atanacağı SAP2000 grubu |
| `ad_desenleri` | Kesit adı desenleri (`*`, `?`), büyük/küçük harf duyarsız. Varsayılan `["*"]` |
| `profil_tipleri` | `I, U, T, L, 2L, 2U, KUTU, BORU, DIKDORTGEN, DAIRE, GENEL, SD`. Boş bırakılırsa hepsi taranır. Otomatik seçim listeleri her zaman hariç tutulur. |
| `geometrik` | Özellik başına `min` ve/veya `max` (birimler aşağıda) |
| `tasarim.oran_max` | Gruptaki çubukların en büyük çelik tasarım oranı için üst sınır. Tasarım hatası veren profil de elenir. |
| `deplasman.max_mm` | Mutlak deplasman sınırı [mm] |
| `deplasman.yon` | `U1`, `U2` veya `U3` (global). Varsayılan `U3` |
| `deplasman.kombinasyonlar` | Deplasmanın okunacağı kombinasyon veya yük durumu adları |
| `deplasman.grup` | Deplasmanın okunacağı grup. Varsayılan `grup` |
| `mod` | `en_hafif`: ilk uygun profilde durur. `tumu`: hepsini değerlendirir |
| `uygula`, `rapor` | Komut satırındaki `--uygula` ve `--rapor` seçeneklerinin varsayılanları |

### Geometrik özellikler (araç SAP2000'i kN-cm birimine alır)

| Anahtar | Anlam | Birim |
|---|---|---|
| `alan`, `as2`, `as3` | Alan ve kesme alanları | cm² |
| `i22`, `i33`, `j` | Atalet momentleri, burulma sabiti | cm⁴ |
| `s22`, `s33` / `z22`, `z33` | Elastik / plastik mukavemet momenti | cm³ |
| `r22`, `r33` | Atalet yarıçapı | cm |
| `t3`, `t2` | Yükseklik, genişlik (I, U, T, L, kutu, boru, dikdörtgen) | cm |
| `kg_m` | Birim ağırlık (alan × malzeme birim hacim ağırlığı) | kg/m |

Araç birimi geçici olarak değiştirir. Çalışma bitince modelin özgün birimi geri yüklenir.

## Yapı

```
profil_secici/
  model.py         Profil, Kosullar: ayar doğrulama, süzgeç ve geometrik kontrol (saf Python)
  secici.py        Tarama döngüsü, seçim, geri yükleme, CSV rapor (saf Python)
  sap_adaptoru.py  SAP2000 OAPI çağrıları (comtypes). Seçicinin kullandığı tek SAP katmanı
  __main__.py      Komut satırı
tests/             SAP2000 gerektirmeyen birim testleri (sahte adaptör)
```

Seçim mantığı `SapArayuzu` protokolüne karşı yazıldı. Yeni bir kontrol eklemek için (ör. beton tasarımı, göreli kat ötelemesi) adaptöre bir metot ve `ProfilSecici._degerlendir` içine bir kontrol eklemek yeterli.

Testler:

```bash
cd sap2000 && python -m unittest -v
```

## Bilinen sınırlar

- Gruptaki **tüm çubuklara aynı profil** atanır. Farklı çubuk grupları için aracı her grupla ayrı çalıştırın. Bu durumda gruplar arasındaki kuvvet etkileşimi sırayla hesaba katılır.
- Deplasman kontrolü mutlak değerle yapılır. Kiriş uçlarına göre göreli sehim (L/300 gibi) şu an desteklenmiyor.
- `sap_adaptoru.py` içindeki OAPI çağrı imzaları dokümantasyona göre yazıldı ve gerçek SAP2000 olmadan test edildi. İlk kullanımda `--listele` ile küçük bir modelde doğrulayın. Sürümler arasında imza farkı olursa sorun yalnızca bu dosyada çıkar.
