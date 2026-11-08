"""Profil ve koşul veri yapıları, SAP2000'den bağımsız saf mantık.

Birimler: Araç SAP2000'i kN-cm-°C birimine alır. Bu yüzden tüm kesit
özellikleri cm cinsindendir (alan cm², atalet cm⁴, mukavemet momenti cm³,
boyutlar cm). Birim ağırlık kg/m, deplasman mm cinsindendir.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any

# SAP2000 eFramePropType kodları → araçta kullanılan kısa adlar.
PROFIL_TIPLERI: dict[int, str] = {
    1: "I",
    2: "U",
    3: "T",
    4: "L",
    5: "2L",
    6: "KUTU",
    7: "BORU",
    8: "DIKDORTGEN",
    9: "DAIRE",
    10: "GENEL",
    11: "2U",
    12: "OTOMATIK",
    13: "SD",
    14: "DEGISKEN",
}

# Otomatik seçim listeleri ve değişken kesitler tekil profil değildir;
# aday olarak hiçbir zaman kullanılmaz.
HARIC_TIPLER = frozenset({"OTOMATIK", "DEGISKEN"})

# Koşul yazılabilecek özellikler ve anlamları (README'de de listelenir).
OZELLIKLER: dict[str, str] = {
    "alan": "Kesit alanı [cm²]",
    "as2": "2 ekseni kesme alanı [cm²]",
    "as3": "3 ekseni kesme alanı [cm²]",
    "j": "Burulma sabiti [cm⁴]",
    "i22": "Zayıf eksen atalet momenti [cm⁴]",
    "i33": "Kuvvetli eksen atalet momenti [cm⁴]",
    "s22": "Zayıf eksen elastik mukavemet momenti [cm³]",
    "s33": "Kuvvetli eksen elastik mukavemet momenti [cm³]",
    "z22": "Zayıf eksen plastik mukavemet momenti [cm³]",
    "z33": "Kuvvetli eksen plastik mukavemet momenti [cm³]",
    "r22": "Zayıf eksen atalet yarıçapı [cm]",
    "r33": "Kuvvetli eksen atalet yarıçapı [cm]",
    "t3": "Kesit yüksekliği [cm]",
    "t2": "Kesit genişliği [cm]",
    "kg_m": "Birim ağırlık [kg/m]",
}

DEPLASMAN_YONLERI = ("U1", "U2", "U3")
MODLAR = ("en_hafif", "tumu")


class AyarHatasi(ValueError):
    """Ayar dosyasındaki geçersiz değerler için."""


@dataclass
class Profil:
    ad: str
    tip: str
    malzeme: str = ""
    ozellikler: dict[str, float | None] = field(default_factory=dict)

    def ozellik(self, anahtar: str) -> float | None:
        return self.ozellikler.get(anahtar)

    @property
    def siralama_anahtari(self) -> tuple[float, float, str]:
        """Hafiften ağıra sıralama: önce kg/m, yoksa alan, sonra ad."""
        kg = self.ozellik("kg_m")
        alan = self.ozellik("alan")
        sonsuz = float("inf")
        return (
            kg if kg is not None else sonsuz,
            alan if alan is not None else sonsuz,
            self.ad,
        )


@dataclass
class Sinir:
    min: float | None = None
    max: float | None = None

    def ihlaller(self, anahtar: str, deger: float | None) -> list[str]:
        if deger is None:
            return [f"{anahtar} okunamadı"]
        nedenler = []
        if self.min is not None and deger < self.min:
            nedenler.append(f"{anahtar}={deger:g} < {self.min:g}")
        if self.max is not None and deger > self.max:
            nedenler.append(f"{anahtar}={deger:g} > {self.max:g}")
        return nedenler


@dataclass
class Kosullar:
    grup: str
    ad_desenleri: list[str] = field(default_factory=lambda: ["*"])
    profil_tipleri: list[str] = field(default_factory=list)
    geometrik: dict[str, Sinir] = field(default_factory=dict)
    oran_max: float | None = None
    deplasman_max_mm: float | None = None
    deplasman_kombinasyonlari: list[str] = field(default_factory=list)
    deplasman_yonu: str = "U3"
    deplasman_grubu: str | None = None

    @property
    def analiz_gerekli(self) -> bool:
        return self.oran_max is not None or self.deplasman_max_mm is not None

    def ad_uyuyor(self, ad: str) -> bool:
        ad_b = ad.upper()
        return any(fnmatch.fnmatchcase(ad_b, d.upper()) for d in self.ad_desenleri)

    def tip_uyuyor(self, tip: str) -> bool:
        if tip in HARIC_TIPLER:
            return False
        return not self.profil_tipleri or tip in self.profil_tipleri

    def geometrik_ihlaller(self, profil: Profil) -> list[str]:
        nedenler: list[str] = []
        for anahtar, sinir in self.geometrik.items():
            nedenler.extend(sinir.ihlaller(anahtar, profil.ozellik(anahtar)))
        return nedenler

    @classmethod
    def sozlukten(cls, veri: dict[str, Any]) -> Kosullar:
        """JSON ayarından ``Kosullar`` üretir ve doğrular."""
        izinli = {
            "grup",
            "ad_desenleri",
            "profil_tipleri",
            "geometrik",
            "tasarim",
            "deplasman",
            "mod",
            "uygula",
            "rapor",
        }
        bilinmeyen = set(veri) - izinli
        if bilinmeyen:
            raise AyarHatasi(f"Bilinmeyen ayar anahtarları: {sorted(bilinmeyen)}")

        grup = veri.get("grup")
        if not isinstance(grup, str) or not grup:
            raise AyarHatasi("'grup' zorunludur (profilin atanacağı SAP2000 grubu).")

        desenler = veri.get("ad_desenleri", ["*"])
        if not isinstance(desenler, list) or not desenler:
            raise AyarHatasi("'ad_desenleri' boş olmayan bir liste olmalı.")

        tipler = [str(t).upper() for t in veri.get("profil_tipleri", [])]
        gecerli_tipler = set(PROFIL_TIPLERI.values()) - HARIC_TIPLER
        hatali = [t for t in tipler if t not in gecerli_tipler]
        if hatali:
            raise AyarHatasi(
                f"Geçersiz profil tipleri: {hatali}. Geçerli: {sorted(gecerli_tipler)}"
            )

        geometrik: dict[str, Sinir] = {}
        for anahtar, sinir in veri.get("geometrik", {}).items():
            anahtar = anahtar.lower()
            if anahtar not in OZELLIKLER:
                raise AyarHatasi(
                    f"Bilinmeyen özellik '{anahtar}'. Geçerli: {sorted(OZELLIKLER)}"
                )
            if not isinstance(sinir, dict) or not set(sinir) <= {"min", "max"}:
                raise AyarHatasi(f"'{anahtar}' için yalnızca 'min'/'max' yazılabilir.")
            if not sinir:
                raise AyarHatasi(f"'{anahtar}' için 'min' veya 'max' verilmeli.")
            geometrik[anahtar] = Sinir(
                min=_sayi(sinir.get("min"), anahtar),
                max=_sayi(sinir.get("max"), anahtar),
            )

        tasarim = veri.get("tasarim", {})
        oran_max = _sayi(tasarim.get("oran_max"), "tasarim.oran_max")
        if oran_max is not None and oran_max <= 0:
            raise AyarHatasi("'tasarim.oran_max' pozitif olmalı.")

        dep = veri.get("deplasman", {})
        dep_max = _sayi(dep.get("max_mm"), "deplasman.max_mm")
        kombolar = list(dep.get("kombinasyonlar", []))
        yon = str(dep.get("yon", "U3")).upper()
        if yon not in DEPLASMAN_YONLERI:
            raise AyarHatasi(f"'deplasman.yon' şunlardan biri olmalı: {DEPLASMAN_YONLERI}")
        if dep_max is not None and not kombolar:
            raise AyarHatasi(
                "'deplasman.max_mm' verildiğinde 'deplasman.kombinasyonlar' zorunludur."
            )

        mod = veri.get("mod", "en_hafif")
        if mod not in MODLAR:
            raise AyarHatasi(f"'mod' şunlardan biri olmalı: {MODLAR}")

        return cls(
            grup=grup,
            ad_desenleri=[str(d) for d in desenler],
            profil_tipleri=tipler,
            geometrik=geometrik,
            oran_max=oran_max,
            deplasman_max_mm=dep_max,
            deplasman_kombinasyonlari=kombolar,
            deplasman_yonu=yon,
            deplasman_grubu=dep.get("grup"),
        )


def _sayi(deger: Any, ad: str) -> float | None:
    if deger is None:
        return None
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        raise AyarHatasi(f"'{ad}' sayı olmalı, verilen: {deger!r}")
    return float(deger)
