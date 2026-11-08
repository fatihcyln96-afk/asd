"""SAP2000 OAPI (comtypes) sarmalayıcısı.

Yalnızca Windows'ta ve SAP2000 kuruluyken çalışır. Seçim mantığı bu modüle
bağımlı değildir, testlerde sahte bir adaptör kullanılır.

comtypes'ta ByRef (çıktı) parametrelerin yerine boş değerler verilir.
Fonksiyon, çıktıları bir liste olarak döndürür ve listenin son elemanı dönüş
kodudur (0 = başarılı). ``_cagir`` bu düzeni tek yerde ele alır.
"""

from __future__ import annotations

from typing import Any

from .model import PROFIL_TIPLERI, Profil
from .secici import TasarimSonucu

KN_CM_C = 13  # eUnits
NESNE, GRUP = 0, 1  # eItemType
NESNE_ELM = 0  # eItemTypeElm.ObjectElm
NOKTA_NESNESI, CUBUK_NESNESI = 1, 2  # GroupDef.GetAssignments nesne tipleri
YERCEKIMI = 9.80665
SAP_PROGID = "CSI.SAP2000.API.SapObject"


class SapHatasi(RuntimeError):
    pass


def _cagir(fonk: Any, *args: Any) -> list[Any]:
    sonuc = fonk(*args)
    if isinstance(sonuc, (list, tuple)):
        *degerler, kod = sonuc
    else:
        degerler, kod = [], sonuc
    if kod != 0:
        ad = getattr(fonk, "__name__", repr(fonk))
        raise SapHatasi(f"{ad}{args[:1]} başarısız (dönüş kodu {kod})")
    return list(degerler)


def baglan(yeni_ac: bool = False, program_yolu: str | None = None, gorunur: bool = True):
    """SAP2000 nesnesini döndürür (``SapObject``).

    Varsayılan olarak açık olan SAP2000'e bağlanır. ``yeni_ac`` verilirse yeni
    bir örnek başlatılır.
    """
    import comtypes.client  # yalnızca Windows'ta mevcut

    helper = comtypes.client.CreateObject("SAP2000v1.Helper")
    helper = helper.QueryInterface(comtypes.gen.SAP2000v1.cHelper)
    if not yeni_ac:
        try:
            return helper.GetObject(SAP_PROGID)
        except OSError as e:  # COMError, OSError'dan türer
            raise SapHatasi(
                "Açık bir SAP2000 bulunamadı. Modeli SAP2000'de açın ya da --yeni-ac kullanın."
            ) from e
    sap = helper.CreateObject(program_yolu) if program_yolu else helper.CreateObjectProgID(SAP_PROGID)
    sap.ApplicationStart(KN_CM_C, gorunur)
    return sap


class SapAdaptoru:
    """``secici.SapArayuzu`` protokolünün gerçek SAP2000 uygulaması.

    Bağlam yöneticisi olarak kullanılır. Girişte birimi kN-cm-°C yapar,
    çıkışta özgün birimi geri yükler.
    """

    def __init__(self, sap_model: Any) -> None:
        self.m = sap_model
        self._ozgun_birim: int | None = None
        self._kombolar: set[str] | None = None

    def __enter__(self) -> SapAdaptoru:
        self._ozgun_birim = self.m.GetPresentUnits()
        _cagir(self.m.SetPresentUnits, KN_CM_C)
        return self

    def __exit__(self, *_: Any) -> None:
        if self._ozgun_birim is not None:
            self.m.SetPresentUnits(self._ozgun_birim)

    # --- Profiller -----------------------------------------------------------

    def profiller(self) -> list[Profil]:
        _, adlar = _cagir(self.m.PropFrame.GetNameList, 0, [])
        return [self._profil_oku(ad) for ad in adlar]

    def _profil_oku(self, ad: str) -> Profil:
        pf = self.m.PropFrame
        (tip_kodu,) = _cagir(pf.GetTypeOAPI, ad)
        tip = PROFIL_TIPLERI.get(tip_kodu, f"TIP{tip_kodu}")
        ozellikler: dict[str, float | None] = {}
        malzeme = ""
        try:
            (alan, as2, as3, j, i22, i33, s22, s33, z22, z33, r22, r33) = _cagir(
                pf.GetSectProps, ad, *([0.0] * 12)
            )
            ozellikler.update(
                alan=alan, as2=as2, as3=as3, j=j, i22=i22, i33=i33,
                s22=s22, s33=s33, z22=z22, z33=z33, r22=r22, r33=r33,
            )
            (malzeme,) = _cagir(pf.GetMaterial, ad, "")
            if malzeme:
                w, _m = _cagir(self.m.PropMaterial.GetWeightAndMass, malzeme, 0.0, 0.0)
                # A [cm²] · γ [kN/cm³] · 100 [cm/m] → kN/m → kg/m
                ozellikler["kg_m"] = alan * w * 100 * 1000 / YERCEKIMI
        except SapHatasi:
            pass  # Otomatik listeler vb. için özellik okunamaz; koşulda elenir.
        ozellikler.update(self._boyutlar(ad, tip))
        return Profil(ad=ad, tip=tip, malzeme=malzeme, ozellikler=ozellikler)

    def _boyutlar(self, ad: str, tip: str) -> dict[str, float | None]:
        """Yükseklik (t3) ve genişlik (t2). Tipi desteklenmiyorsa boş döner."""
        pf = self.m.PropFrame
        # İmzalar: Name, FileName, MatProp, T3, T2/TW, [Tf, Tw, [T2b, Tfb]], Color, Notes, GUID
        cagrilar = {
            "I": (pf.GetISection, 6),
            "U": (pf.GetChannel, 4),
            "T": (pf.GetTee, 4),
            "L": (pf.GetAngle, 4),
            "KUTU": (pf.GetTube, 4),
            "DIKDORTGEN": (pf.GetRectangle, 2),
            "BORU": (pf.GetPipe, 2),
        }
        if tip not in cagrilar:
            return {}
        fonk, sayisal = cagrilar[tip]
        try:
            degerler = _cagir(fonk, ad, "", "", *([0.0] * sayisal), 0, "", "")
        except (SapHatasi, TypeError, OSError):
            return {}
        t3 = degerler[2]
        t2 = t3 if tip == "BORU" else degerler[3]
        return {"t3": t3, "t2": t2}

    # --- Atama ---------------------------------------------------------------

    def grup_cubuklari(self, grup: str) -> list[str]:
        return [ad for tip, ad in self._grup_atamalari(grup) if tip == CUBUK_NESNESI]

    def _grup_atamalari(self, grup: str) -> list[tuple[int, str]]:
        _, tipler, adlar = _cagir(self.m.GroupDef.GetAssignments, grup, 0, [], [])
        return list(zip(tipler, adlar))

    def cubuk_kesiti(self, cubuk: str) -> str:
        kesit, _otomatik = _cagir(self.m.FrameObj.GetSection, cubuk, "", "")
        return kesit

    def cubuk_kesiti_ata(self, cubuk: str, kesit: str) -> None:
        _cagir(self.m.FrameObj.SetSection, cubuk, kesit, NESNE)

    def grup_kesiti_ata(self, grup: str, kesit: str) -> None:
        _cagir(self.m.FrameObj.SetSection, grup, kesit, GRUP)

    # --- Analiz ve tasarım ---------------------------------------------------

    def kilidi_ac(self) -> None:
        if self.m.GetModelIsLocked():
            _cagir(self.m.SetModelIsLocked, False)

    def analiz_et(self) -> None:
        if not self.m.GetModelFilename():
            raise SapHatasi("Analiz için model önce bir .sdb dosyasına kaydedilmeli.")
        _cagir(self.m.Analyze.RunAnalysis)

    def celik_tasarim(self, grup: str) -> list[TasarimSonucu]:
        ds = self.m.DesignSteel
        _cagir(ds.StartDesign)
        _, cubuklar, oranlar, _tip, _yer, kombolar, hatalar, _uyari = _cagir(
            ds.GetSummaryResults, grup, 0, [], [], [], [], [], [], [], GRUP
        )
        return [
            TasarimSonucu(cubuk=c, oran=o, kombinasyon=k, hata=h or "")
            for c, o, k, h in zip(cubuklar, oranlar, kombolar, hatalar)
        ]

    def max_deplasman_mm(self, grup: str, kombinasyonlar: list[str], yon: str) -> float:
        noktalar = self._grup_noktalari(grup)
        if not noktalar:
            raise SapHatasi(f"'{grup}' grubunda deplasman okunacak nokta yok.")
        kurulum = self.m.Results.Setup
        _cagir(kurulum.DeselectAllCasesAndCombosForOutput)
        for ad in kombinasyonlar:
            if ad in self._kombinasyonlar():
                _cagir(kurulum.SetComboSelectedForOutput, ad)
            else:
                _cagir(kurulum.SetCaseSelectedForOutput, ad)

        indeks = {"U1": 0, "U2": 1, "U3": 2}[yon]
        en_buyuk = 0.0
        for nokta in noktalar:
            sonuc = _cagir(
                self.m.Results.JointDispl, nokta, NESNE_ELM, 0, *([[]] * 11)
            )
            # [n, Obj, Elm, LoadCase, StepType, StepNum, U1, U2, U3, R1, R2, R3]
            degerler = sonuc[6 + indeks]
            if degerler:
                en_buyuk = max(en_buyuk, max(abs(d) for d in degerler))
        return en_buyuk * 10.0  # cm → mm

    def _grup_noktalari(self, grup: str) -> list[str]:
        noktalar: dict[str, None] = {}  # sıralı küme
        for tip, ad in self._grup_atamalari(grup):
            if tip == NOKTA_NESNESI:
                noktalar[ad] = None
            elif tip == CUBUK_NESNESI:
                i, j = _cagir(self.m.FrameObj.GetPoints, ad, "", "")
                noktalar[i] = None
                noktalar[j] = None
        return list(noktalar)

    def _kombinasyonlar(self) -> set[str]:
        if self._kombolar is None:
            _, adlar = _cagir(self.m.RespCombo.GetNameList, 0, [])
            self._kombolar = set(adlar or [])
        return self._kombolar
