"""Profil tarama ve seçim algoritması.

Algoritma:
1. Modeldeki tüm çubuk kesitleri okunur; ad deseni ve tipe göre süzülür.
2. Adaylar hafiften ağıra sıralanır (kg/m, yoksa alan).
3. Her aday için geometrik koşullar kontrol edilir. Gerekiyorsa profil gruba
   atanır, analiz ve çelik tasarımı çalıştırılır; oran ve deplasman kontrol edilir.
   Her adımda yeniden analiz yapıldığı için hiperstatik sistemlerde rijitlik
   değişiminden kaynaklanan kuvvet dağılımı da hesaba katılır.
4. ``en_hafif`` modunda ilk uygun profilde durulur. Adaylar hafiften ağıra
   sırayla denendiği için bu profil uygun olanların en hafifidir. ``tumu``
   modunda bütün adaylar değerlendirilip rapora yazılır.
5. Sonda çubukların özgün kesitleri geri yüklenir. ``uygula`` açıksa seçilen
   profil grupta bırakılır.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .model import Kosullar, Profil


@dataclass
class TasarimSonucu:
    cubuk: str
    oran: float
    kombinasyon: str = ""
    hata: str = ""


class SapArayuzu(Protocol):
    """Seçicinin SAP2000'den beklediği işlemler (bkz. ``sap_adaptoru``)."""

    def profiller(self) -> list[Profil]: ...
    def grup_cubuklari(self, grup: str) -> list[str]: ...
    def cubuk_kesiti(self, cubuk: str) -> str: ...
    def cubuk_kesiti_ata(self, cubuk: str, kesit: str) -> None: ...
    def grup_kesiti_ata(self, grup: str, kesit: str) -> None: ...
    def kilidi_ac(self) -> None: ...
    def analiz_et(self) -> None: ...
    def celik_tasarim(self, grup: str) -> list[TasarimSonucu]: ...
    def max_deplasman_mm(self, grup: str, kombinasyonlar: list[str], yon: str) -> float: ...


@dataclass
class Sonuc:
    profil: Profil
    uygun: bool
    nedenler: list[str] = field(default_factory=list)
    analiz_edildi: bool = False
    oran: float | None = None
    kritik_cubuk: str = ""
    kritik_kombinasyon: str = ""
    deplasman_mm: float | None = None


@dataclass
class SecimRaporu:
    secilen: Profil | None
    sonuclar: list[Sonuc]
    uygulandi: bool = False

    def csv_yaz(self, yol: str | Path) -> None:
        anahtarlar = ["alan", "i33", "s33", "z33", "i22", "t3", "t2"]
        with open(yol, "w", newline="", encoding="utf-8-sig") as f:
            yazici = csv.writer(f, delimiter=";")
            yazici.writerow(
                ["profil", "tip", "kg_m", *anahtarlar, "oran", "kritik_cubuk",
                 "kritik_kombinasyon", "deplasman_mm", "uygun", "nedenler"]
            )
            for s in self.sonuclar:
                p = s.profil
                yazici.writerow(
                    [p.ad, p.tip, _bicim(p.ozellik("kg_m")),
                     *(_bicim(p.ozellik(a)) for a in anahtarlar),
                     _bicim(s.oran), s.kritik_cubuk, s.kritik_kombinasyon,
                     _bicim(s.deplasman_mm), "EVET" if s.uygun else "HAYIR",
                     " | ".join(s.nedenler)]
                )


class SeciciHatasi(RuntimeError):
    pass


class ProfilSecici:
    def __init__(
        self,
        sap: SapArayuzu,
        kosullar: Kosullar,
        gunluk: Callable[[str], None] = print,
    ) -> None:
        self.sap = sap
        self.k = kosullar
        self.gunluk = gunluk

    def adaylar(self) -> list[Profil]:
        """Ad ve tip süzgecinden geçen profiller, hafiften ağıra."""
        uygun = [
            p for p in self.sap.profiller()
            if self.k.ad_uyuyor(p.ad) and self.k.tip_uyuyor(p.tip)
        ]
        return sorted(uygun, key=lambda p: p.siralama_anahtari)

    def calistir(self, mod: str = "en_hafif", uygula: bool = False) -> SecimRaporu:
        adaylar = self.adaylar()
        if not adaylar:
            raise SeciciHatasi(
                "Süzgeçlere uyan profil yok. 'ad_desenleri' ve 'profil_tipleri' "
                "ayarlarını kontrol edin."
            )

        cubuklar = self.sap.grup_cubuklari(self.k.grup)
        if not cubuklar:
            raise SeciciHatasi(f"'{self.k.grup}' grubunda çubuk (frame) yok.")
        ozgun = {c: self.sap.cubuk_kesiti(c) for c in cubuklar}

        self.gunluk(
            f"{len(adaylar)} aday profil, '{self.k.grup}' grubunda "
            f"{len(cubuklar)} çubuk. Mod: {mod}"
        )

        sonuclar: list[Sonuc] = []
        secilen: Profil | None = None
        son_analiz: Profil | None = None  # modelde en son analiz edilen profil
        uygulandi = False
        try:
            for i, profil in enumerate(adaylar, 1):
                sonuc = self._degerlendir(profil)
                if sonuc.analiz_edildi:
                    son_analiz = profil
                sonuclar.append(sonuc)
                self.gunluk(f"[{i}/{len(adaylar)}] {_ozet(sonuc)}")
                if sonuc.uygun and secilen is None:
                    secilen = profil
                    if mod == "en_hafif":
                        break

            if uygula and secilen is not None:
                if son_analiz is not secilen:
                    # Model başka bir profille analiz edilmiş ya da hiç analiz
                    # edilmemiş: seçileni ata. Gerekirse sonuçları güncelle.
                    self.sap.kilidi_ac()
                    self.sap.grup_kesiti_ata(self.k.grup, secilen.ad)
                    if self.k.analiz_gerekli:
                        self.sap.analiz_et()
                uygulandi = True
        finally:
            if not uygulandi:
                self._geri_yukle(ozgun)

        if secilen is None:
            self.gunluk("Koşulları sağlayan profil bulunamadı.")
        else:
            durum = "gruba atandı" if uygulandi else "model değiştirilmedi"
            self.gunluk(f"Seçilen profil: {secilen.ad} ({durum})")
        return SecimRaporu(secilen=secilen, sonuclar=sonuclar, uygulandi=uygulandi)

    def _degerlendir(self, profil: Profil) -> Sonuc:
        nedenler = self.k.geometrik_ihlaller(profil)
        if nedenler or not self.k.analiz_gerekli:
            return Sonuc(profil=profil, uygun=not nedenler, nedenler=nedenler)

        self.sap.kilidi_ac()
        self.sap.grup_kesiti_ata(self.k.grup, profil.ad)
        self.sap.analiz_et()
        sonuc = Sonuc(profil=profil, uygun=True, analiz_edildi=True)

        if self.k.oran_max is not None:
            tasarim = self.sap.celik_tasarim(self.k.grup)
            if not tasarim:
                sonuc.nedenler.append("tasarım sonucu yok")
            else:
                kritik = max(tasarim, key=lambda t: t.oran)
                sonuc.oran = kritik.oran
                sonuc.kritik_cubuk = kritik.cubuk
                sonuc.kritik_kombinasyon = kritik.kombinasyon
                if kritik.oran > self.k.oran_max:
                    sonuc.nedenler.append(f"oran={kritik.oran:.3f} > {self.k.oran_max:g}")
                hatalilar = [t for t in tasarim if t.hata.strip()]
                if hatalilar:
                    ornek = hatalilar[0]
                    sonuc.nedenler.append(
                        f"tasarım hatası ({len(hatalilar)} çubuk, ör. "
                        f"{ornek.cubuk}: {ornek.hata.strip()})"
                    )

        if self.k.deplasman_max_mm is not None:
            d = self.sap.max_deplasman_mm(
                self.k.deplasman_grubu or self.k.grup,
                self.k.deplasman_kombinasyonlari,
                self.k.deplasman_yonu,
            )
            sonuc.deplasman_mm = d
            if d > self.k.deplasman_max_mm:
                sonuc.nedenler.append(
                    f"{self.k.deplasman_yonu}={d:.2f} mm > {self.k.deplasman_max_mm:g} mm"
                )

        sonuc.uygun = not sonuc.nedenler
        return sonuc

    def _geri_yukle(self, ozgun: dict[str, str]) -> None:
        self.sap.kilidi_ac()
        for cubuk, kesit in ozgun.items():
            self.sap.cubuk_kesiti_ata(cubuk, kesit)
        self.gunluk("Özgün kesitler geri yüklendi.")


def _bicim(deger: float | None) -> str:
    return "" if deger is None else f"{deger:.4g}"


def _ozet(s: Sonuc) -> str:
    parcalar = [s.profil.ad]
    if s.oran is not None:
        parcalar.append(f"oran={s.oran:.3f}")
    if s.deplasman_mm is not None:
        parcalar.append(f"dep={s.deplasman_mm:.2f}mm")
    parcalar.append("UYGUN" if s.uygun else "uygun değil: " + "; ".join(s.nedenler))
    return "  ".join(parcalar)
