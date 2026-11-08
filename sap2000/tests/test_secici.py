"""SAP2000 gerektirmeyen testler: sahte bir adaptörle seçim mantığını doğrular."""

import csv
import tempfile
import unittest
from pathlib import Path

from profil_secici import (
    AyarHatasi,
    Kosullar,
    Profil,
    ProfilSecici,
    SeciciHatasi,
    TasarimSonucu,
)


def ipe(ad, kg, i33, t3):
    return Profil(ad=ad, tip="I", malzeme="S275",
                  ozellikler={"kg_m": kg, "alan": kg / 0.785, "i33": i33, "t3": t3})


PROFILLER = [
    ipe("IPE300", 42.2, 8356, 30),
    ipe("IPE200", 22.4, 1943, 20),
    ipe("IPE240", 30.7, 3892, 24),
    ipe("IPE270", 36.1, 5790, 27),
    ipe("HEA200", 42.3, 3692, 19),
    Profil(ad="KIRIS_OTO", tip="OTOMATIK"),
    Profil(ad="KUTU100", tip="KUTU", ozellikler={"kg_m": 10.0, "i33": 300}),
]


class SahteSap:
    """Oran ve deplasman i33 ile ters orantılı: rijitlik arttıkça düşer."""

    def __init__(self, profiller=PROFILLER, cubuklar=("B1", "B2"), hata_veren=()):
        self._profiller = profiller
        self.kesitler = {c: "ESKI" for c in cubuklar}
        self.analiz_sayisi = 0
        self.hata_veren = set(hata_veren)
        self.analiz_patlat = False

    def profiller(self):
        return list(self._profiller)

    def grup_cubuklari(self, grup):
        return list(self.kesitler)

    def cubuk_kesiti(self, cubuk):
        return self.kesitler[cubuk]

    def cubuk_kesiti_ata(self, cubuk, kesit):
        self.kesitler[cubuk] = kesit

    def grup_kesiti_ata(self, grup, kesit):
        for c in self.kesitler:
            self.kesitler[c] = kesit

    def kilidi_ac(self):
        pass

    def _i33(self):
        ad = next(iter(self.kesitler.values()))
        return next(p for p in self._profiller if p.ad == ad).ozellikler["i33"]

    def analiz_et(self):
        if self.analiz_patlat:
            raise RuntimeError("analiz çöktü")
        self.analiz_sayisi += 1

    def celik_tasarim(self, grup):
        ad = next(iter(self.kesitler.values()))
        oran = 4000 / self._i33()
        return [
            TasarimSonucu("B1", oran, "COMB1", "hata" if ad in self.hata_veren else ""),
            TasarimSonucu("B2", oran * 0.8, "COMB2"),
        ]

    def max_deplasman_mm(self, grup, kombinasyonlar, yon):
        return 60000 / self._i33()


def kosul(**ek):
    temel = {"grup": "KIRISLER", "ad_desenleri": ["IPE*", "HEA*"]}
    temel.update(ek)
    return Kosullar.sozlukten(temel)


def sessiz(_):
    pass


class AdayTesti(unittest.TestCase):
    def test_desen_tip_suzgeci_ve_siralama(self):
        s = ProfilSecici(SahteSap(), kosul(), gunluk=sessiz)
        self.assertEqual(
            [p.ad for p in s.adaylar()],
            ["IPE200", "IPE240", "IPE270", "IPE300", "HEA200"],
        )

    def test_otomatik_liste_her_zaman_haric(self):
        s = ProfilSecici(SahteSap(), kosul(ad_desenleri=["*"]), gunluk=sessiz)
        adlar = [p.ad for p in s.adaylar()]
        self.assertNotIn("KIRIS_OTO", adlar)
        self.assertIn("KUTU100", adlar)

    def test_tip_suzgeci(self):
        s = ProfilSecici(SahteSap(), kosul(ad_desenleri=["*"], profil_tipleri=["kutu"]),
                         gunluk=sessiz)
        self.assertEqual([p.ad for p in s.adaylar()], ["KUTU100"])

    def test_desen_buyuk_kucuk_harf_duyarsiz(self):
        s = ProfilSecici(SahteSap(), kosul(ad_desenleri=["ipe2?0"]), gunluk=sessiz)
        self.assertEqual([p.ad for p in s.adaylar()], ["IPE200", "IPE240", "IPE270"])


class SecimTesti(unittest.TestCase):
    def test_yalniz_geometrik_kosul_analiz_yapmaz(self):
        sap = SahteSap()
        r = ProfilSecici(sap, kosul(geometrik={"i33": {"min": 5000}}), gunluk=sessiz).calistir()
        self.assertEqual(r.secilen.ad, "IPE270")
        self.assertEqual(sap.analiz_sayisi, 0)

    def test_yukseklik_siniri_daha_agir_profile_yonlendirir(self):
        r = ProfilSecici(
            SahteSap(), kosul(geometrik={"i33": {"min": 3500}, "t3": {"max": 20}}), gunluk=sessiz
        ).calistir()
        self.assertEqual(r.secilen.ad, "HEA200")

    def test_oran_kosulu_en_hafifte_durur(self):
        sap = SahteSap()
        # oran = 4000/i33 → IPE200 2.06, IPE240 1.03, IPE270 0.69
        r = ProfilSecici(sap, kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir()
        self.assertEqual(r.secilen.ad, "IPE270")
        self.assertEqual(sap.analiz_sayisi, 3)
        self.assertEqual(r.sonuclar[-1].kritik_cubuk, "B1")
        self.assertEqual(r.sonuclar[-1].kritik_kombinasyon, "COMB1")

    def test_oran_ve_deplasman_birlikte(self):
        # deplasman = 60000/i33 → IPE270 10.4 mm, IPE300 7.2 mm
        r = ProfilSecici(
            SahteSap(),
            kosul(tasarim={"oran_max": 0.95},
                  deplasman={"max_mm": 8, "kombinasyonlar": ["SERV"]}),
            gunluk=sessiz,
        ).calistir()
        self.assertEqual(r.secilen.ad, "IPE300")
        self.assertIn("U3=10.36 mm > 8 mm", r.sonuclar[-2].nedenler)

    def test_tasarim_hatasi_profili_eler(self):
        r = ProfilSecici(SahteSap(hata_veren={"IPE270"}),
                         kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir()
        self.assertEqual(r.secilen.ad, "IPE300")

    def test_tumu_modu_hepsini_degerlendirir(self):
        sap = SahteSap()
        r = ProfilSecici(sap, kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir(mod="tumu")
        self.assertEqual(r.secilen.ad, "IPE270")
        self.assertEqual(len(r.sonuclar), 5)
        self.assertEqual(sap.analiz_sayisi, 5)

    def test_uygun_profil_yoksa_none(self):
        r = ProfilSecici(SahteSap(), kosul(tasarim={"oran_max": 0.1}), gunluk=sessiz).calistir()
        self.assertIsNone(r.secilen)
        self.assertEqual(len(r.sonuclar), 5)

    def test_bos_grup_hata(self):
        with self.assertRaises(SeciciHatasi):
            ProfilSecici(SahteSap(cubuklar=()), kosul(), gunluk=sessiz).calistir()


class ModelDurumuTesti(unittest.TestCase):
    def test_uygula_kapaliyken_ozgun_kesitler_geri_yuklenir(self):
        sap = SahteSap()
        ProfilSecici(sap, kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir()
        self.assertEqual(set(sap.kesitler.values()), {"ESKI"})

    def test_uygula_secileni_birakir_ve_ek_analiz_yapmaz(self):
        sap = SahteSap()
        ProfilSecici(sap, kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir(uygula=True)
        self.assertEqual(set(sap.kesitler.values()), {"IPE270"})
        self.assertEqual(sap.analiz_sayisi, 3)

    def test_tumu_modunda_uygula_secileni_atayip_yeniden_analiz_eder(self):
        sap = SahteSap()
        ProfilSecici(sap, kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir(
            mod="tumu", uygula=True)
        self.assertEqual(set(sap.kesitler.values()), {"IPE270"})
        self.assertEqual(sap.analiz_sayisi, 6)

    def test_hata_olursa_da_geri_yuklenir(self):
        sap = SahteSap()
        sap.analiz_patlat = True
        with self.assertRaises(RuntimeError):
            ProfilSecici(sap, kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir(uygula=True)
        self.assertEqual(set(sap.kesitler.values()), {"ESKI"})


class AyarTesti(unittest.TestCase):
    def test_bilinmeyen_anahtar(self):
        with self.assertRaises(AyarHatasi):
            kosul(grupp="X")

    def test_bilinmeyen_ozellik(self):
        with self.assertRaises(AyarHatasi):
            kosul(geometrik={"atalet": {"min": 1}})

    def test_bos_sinir(self):
        with self.assertRaises(AyarHatasi):
            kosul(geometrik={"i33": {}})

    def test_deplasman_kombinasyonsuz(self):
        with self.assertRaises(AyarHatasi):
            kosul(deplasman={"max_mm": 10})

    def test_sayi_olmayan_deger(self):
        with self.assertRaises(AyarHatasi):
            kosul(tasarim={"oran_max": "0.9"})

    def test_grup_zorunlu(self):
        with self.assertRaises(AyarHatasi):
            Kosullar.sozlukten({})

    def test_ornek_ayar_dosyasi_gecerli(self):
        import json
        yol = Path(__file__).resolve().parent.parent / "ornek_ayar.json"
        k = Kosullar.sozlukten(json.loads(yol.read_text(encoding="utf-8")))
        self.assertTrue(k.analiz_gerekli)


class RaporTesti(unittest.TestCase):
    def test_csv(self):
        r = ProfilSecici(SahteSap(), kosul(tasarim={"oran_max": 0.95}), gunluk=sessiz).calistir(
            mod="tumu")
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "rapor.csv"
            r.csv_yaz(yol)
            with open(yol, encoding="utf-8-sig") as f:
                satirlar = list(csv.reader(f, delimiter=";"))
        self.assertEqual(satirlar[0][0], "profil")
        self.assertEqual(len(satirlar), 6)
        uygunluk = {s[0]: s[-2] for s in satirlar[1:]}
        self.assertEqual(uygunluk["IPE200"], "HAYIR")
        self.assertEqual(uygunluk["IPE270"], "EVET")


if __name__ == "__main__":
    unittest.main()
