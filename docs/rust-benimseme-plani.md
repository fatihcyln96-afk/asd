# Rust Benimseme Planı

> **Durum:** Taslak · **Hazırlanma:** Kasım 2026
> **Varsayım:** Bu plan yazılırken depoda mevcut bir proje yoktu. Bu yüzden genel bir yol haritası olarak hazırlandı. Mevcut projelerin dili, ekip büyüklüğü ve hedefler netleştiğinde güncellenmelidir.

## 1. Amaç

Rust'ı ekibin projelerine **kontrollü ve ölçülebilir** bir şekilde dahil etmek. Öncelikli olarak şu alanlarda kullanılacak:

- Performansın kritik olduğu servis ve bileşenler
- Bellek güvenliğinin önemli olduğu sistem seviyesindeki kodlar
- Komut satırı araçları ve iç araçlar

Hedef "her şeyi Rust'a taşımak" değildir. Rust, gerçekten değer kattığı yerlerde kullanılacak.

## 2. Başarı Kriterleri

| Kriter | Hedef |
|--------|-------|
| Rust ile çalışabilen geliştirici sayısı | İlk 3 ayda ekibin en az %50'si |
| Üretimde çalışan Rust bileşeni | 6 ay içinde en az 1 |
| Pilot bileşende performans kazancı | Mevcut çözüme göre ölçülebilir iyileşme (gecikme, CPU, bellek) |
| Üretimde bellek kaynaklı hata | 0 |
| CI'da test kapsamı | Rust kodu için en az %70 |

## 3. Aşamalar

### Aşama 0 — Hazırlık (1–2 hafta)

- [ ] Mevcut projelerin envanterini çıkar: dil, darboğazlar, bakım yükü, hata geçmişi
- [ ] Rust için aday bileşenleri belirle (bkz. Bölüm 4)
- [ ] Bir **Rust sorumlusu** (champion) ata
- [ ] Geliştirme ortamı standardını yayımla: `rustup`, `rust-analyzer`, `rustfmt`, `clippy`
- [ ] `rust-toolchain.toml` ile sabit bir sürüm belirle (ör. stable kanalı, en güncel kararlı sürüm)

### Aşama 1 — Eğitim (3–6 hafta, Aşama 2 ile paralel yürüyebilir)

| Hafta | Konu | Kaynak |
|-------|------|--------|
| 1 | Temel sözdizimi, Cargo, sahiplik | The Rust Book böl. 1–4, Rustlings |
| 2 | Struct, enum, desen eşleme, hata yönetimi | Book böl. 5–9 |
| 3 | Generic, trait, lifetime | Book böl. 10, Rust by Example |
| 4 | Koleksiyonlar, iterator, closure, test | Book böl. 11–13 |
| 5 | Eşzamanlılık, akıllı işaretçiler | Book böl. 15–16 |
| 6 | Async (Tokio), ekosistem (serde, tracing) | Tokio tutorial |

- Haftalık 1 saatlik **kod okuma / soru-cevap** oturumu
- Her geliştirici Exercism Rust parkurundan en az 10 alıştırma tamamlar
- Eğitimin sonunda küçük bir **iç araç** (CLI) yazılır

### Aşama 2 — Pilot Proje (6–8 hafta)

**Seçim ölçütleri:**

- Kapsamı sınırlı ve iyi tanımlı olmalı
- Kritik iş akışını durdurmamalı (geri dönüş planı olmalı)
- Ölçülebilir bir performans veya güvenilirlik hedefi olmalı
- Mevcut sistemle net bir arayüzü olmalı (HTTP/gRPC API, CLI, kütüphane)

**Uygun pilot örnekleri:**

1. Yoğun veri işleyen bir iş (log ayrıştırma, dosya dönüştürme, ETL adımı)
2. Yüksek trafikli, basit bir mikroservis
3. Ekibin günlük kullandığı bir komut satırı aracı
4. Mevcut bir uygulamadaki yavaş bir modülün Rust ile yeniden yazılması (FFI ile)

**Teslimatlar:**

- [ ] Kodun çalışır hali + testler
- [ ] Eski çözümle karşılaştırmalı benchmark raporu
- [ ] Geliştirme deneyimi üzerine ekip geri bildirimi (anket)
- [ ] Devam et / dur kararı için kısa değerlendirme belgesi

### Aşama 3 — Standartlaşma (4 hafta)

- [ ] Proje şablonu (`cargo generate` şablonu veya şablon depo)
- [ ] Kodlama kuralları ve kod inceleme kontrol listesi
- [ ] Onaylı crate listesi (bkz. Bölüm 5)
- [ ] CI/CD şablonu (bkz. Bölüm 6)
- [ ] Güvenlik denetimi süreci: `cargo audit`, `cargo deny`

### Aşama 4 — Yaygınlaştırma (sürekli)

- Yeni projelerde Rust'ı **uygun olduğunda** değerlendir (bkz. Bölüm 7, karar matrisi)
- Mevcut projelerde darboğaz bileşenleri adım adım taşı (strangler fig deseni)
- Her çeyrekte değerlendirme yap: metrikler, sorunlar, eğitim ihtiyaçları

## 4. Mevcut Projelerle Entegrasyon Stratejileri

| Mevcut dil | Entegrasyon yöntemi | Araç |
|-----------|---------------------|------|
| Python | Rust ile yerel eklenti modülü | [PyO3](https://pyo3.rs) + maturin |
| Node.js / TypeScript | Yerel eklenti veya WebAssembly | napi-rs, wasm-bindgen |
| C / C++ | FFI ile çift yönlü çağrı | bindgen, cbindgen, cxx |
| Java / Kotlin | JNI | jni crate |
| Go / diğer | Ayrı servis olarak (HTTP/gRPC) | Axum, Tonic |
| Tarayıcı (frontend) | WebAssembly | wasm-pack |

**Önerilen yaklaşım:** Önce **ayrı servis** veya **CLI** olarak başla. Arayüz netleşmeden FFI karmaşıklığına girme.

## 5. Önerilen Crate (Kütüphane) Seti

| Alan | Crate |
|------|-------|
| Async çalışma zamanı | `tokio` |
| Web framework | `axum` |
| gRPC | `tonic` |
| Serileştirme | `serde`, `serde_json` |
| Veritabanı | `sqlx` (async, derleme zamanında sorgu kontrolü) |
| HTTP istemcisi | `reqwest` |
| Hata yönetimi | `thiserror` (kütüphaneler), `anyhow` (uygulamalar) |
| Loglama / izleme | `tracing`, `tracing-subscriber` |
| CLI argümanları | `clap` |
| Yapılandırma | `config` veya `figment` |
| Test | `proptest`, `insta`, `mockall` |
| Benchmark | `criterion` |

## 6. CI/CD Şablonu (Taslak)

```yaml
# .github/workflows/rust.yml
name: Rust CI
on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - uses: Swatinem/rust-cache@v2
      - run: cargo fmt --all -- --check
      - run: cargo clippy --all-targets -- -D warnings
      - run: cargo test --all
      - run: cargo install cargo-audit && cargo audit
```

## 7. Karar Matrisi: Rust Ne Zaman Kullanılmalı?

| Durum | Rust? |
|-------|-------|
| Düşük gecikme veya yüksek verim kritik | ✅ Evet |
| Bellek güvenliği ve güvenilirlik kritik | ✅ Evet |
| CLI aracı, tek dosya olarak dağıtılacak | ✅ Evet |
| Gömülü sistem / WebAssembly | ✅ Evet |
| Hızlı prototip, gereksinimler belirsiz | ❌ Hayır (Python/TS daha uygun) |
| Basit CRUD uygulaması, ekipte Rust deneyimi yok | ⚠️ Genelde hayır |
| Veri bilimi / ML deneyleri | ❌ Hayır (Rust ile yazılmış Python kütüphaneleri hariç) |

## 8. Riskler ve Önlemler

| Risk | Etki | Önlem |
|------|------|-------|
| Dik öğrenme eğrisi, başta düşük verim | Yüksek | Eğitim takvimi, eşli programlama, pilotu kritik yoldan uzak tutma |
| Derleme sürelerinin uzaması | Orta | `rust-cache`, `sccache`, workspace yapısı, `cargo check` alışkanlığı |
| Ekipte bilginin tek kişide toplanması | Yüksek | En az 2–3 kişiyi derinlemesine yetiştirme, kod incelemelerinde rotasyon |
| Ekosistemde eksik kütüphane | Düşük–Orta | Pilot öncesi bağımlılık araştırması, gerekirse FFI |
| İşe alım zorluğu | Orta | Mevcut ekibi yetiştirmeye öncelik verme |
| `unsafe` kodun kötüye kullanımı | Orta | `unsafe` için zorunlu ek inceleme, `#![forbid(unsafe_code)]` varsayılan |

## 9. Tahmini Zaman Çizelgesi

```
Ay:        1        2        3        4        5        6
Hazırlık   ██
Eğitim     ████████████
Pilot          ████████████████
Standart                       ████████
Yaygın.                                ████████████████ →
                               ▲                ▲
                       Pilot değerlendirme   Çeyrek değerlendirme
```

## 10. Sonraki Adımlar

1. Mevcut projelerin listesini ve kullanılan dilleri paylaşın. Plan bu bilgiyle somutlaştırılacak.
2. Pilot için 2–3 aday bileşen belirleyin.
3. Rust sorumlusunu atayın ve eğitim takvimini başlatın.
