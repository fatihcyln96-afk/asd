"""Komut satırı: ``python -m profil_secici ayar.json [seçenekler]``"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import AyarHatasi, Kosullar, OZELLIKLER
from .secici import ProfilSecici, SeciciHatasi


def _arguman_ayristirici() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m profil_secici",
        description="SAP2000 modelindeki profilleri tarar, koşulları sağlayan en hafif profili seçer.",
    )
    p.add_argument("ayar", type=Path, help="JSON ayar dosyası (bkz. ornek_ayar.json)")
    p.add_argument("--yeni-ac", metavar="MODEL.sdb", type=Path,
                   help="Açık SAP2000'e bağlanmak yerine yeni örnek başlatıp bu modeli aç")
    p.add_argument("--sap-yolu", help="Belirli bir SAP2000.exe sürümü (yalnızca --yeni-ac ile)")
    p.add_argument("--gizli", action="store_true", help="Yeni açılan SAP2000 penceresini gizle")
    p.add_argument("--mod", choices=["en_hafif", "tumu"], help="Ayar dosyasındaki 'mod' değerini ezer")
    p.add_argument("--uygula", action="store_true", help="Seçilen profili grupta bırak")
    p.add_argument("--kaydet", action="store_true", help="Bitince modeli kaydet")
    p.add_argument("--rapor", type=Path, help="CSV rapor yolu (ayar dosyasındaki 'rapor'u ezer)")
    p.add_argument("--listele", action="store_true",
                   help="Analiz yapmadan yalnızca aday profilleri ve özelliklerini listele")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _arguman_ayristirici().parse_args(argv)
    try:
        ayar = json.loads(args.ayar.read_text(encoding="utf-8"))
        kosullar = Kosullar.sozlukten(ayar)
    except (OSError, json.JSONDecodeError, AyarHatasi) as e:
        print(f"Ayar hatası: {e}", file=sys.stderr)
        return 2

    mod = args.mod or ayar.get("mod", "en_hafif")
    uygula = args.uygula or bool(ayar.get("uygula", False))
    rapor_yolu = args.rapor or (Path(ayar["rapor"]) if ayar.get("rapor") else None)

    from .sap_adaptoru import SapAdaptoru, SapHatasi, baglan

    try:
        import comtypes.client  # noqa: F401
    except ImportError:
        print("comtypes bulunamadı. Windows'ta 'pip install comtypes' çalıştırın.", file=sys.stderr)
        return 1

    try:
        sap = baglan(yeni_ac=args.yeni_ac is not None, program_yolu=args.sap_yolu,
                     gorunur=not args.gizli)
        model = sap.SapModel
        if args.yeni_ac is not None:
            if model.File.OpenFile(str(args.yeni_ac.resolve())) != 0:
                raise SapHatasi(f"Model açılamadı: {args.yeni_ac}")

        with SapAdaptoru(model) as adaptor:
            secici = ProfilSecici(adaptor, kosullar)
            if args.listele:
                _listele(secici)
                return 0
            rapor = secici.calistir(mod=mod, uygula=uygula)
        if rapor_yolu:
            rapor.csv_yaz(rapor_yolu)
            print(f"Rapor yazıldı: {rapor_yolu}")
        if args.kaydet and model.File.Save() != 0:
            raise SapHatasi("Model kaydedilemedi.")
    except (SapHatasi, SeciciHatasi) as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1
    return 0 if rapor.secilen is not None else 3


def _listele(secici: ProfilSecici) -> None:
    sutunlar = ["kg_m", "alan", "i33", "s33", "z33", "i22", "t3", "t2"]
    print(f"{'profil':<16}{'tip':<12}" + "".join(f"{s:>11}" for s in sutunlar) + "  geometrik")
    for p in secici.adaylar():
        degerler = "".join(
            f"{p.ozellik(s):>11.4g}" if p.ozellik(s) is not None else f"{'-':>11}"
            for s in sutunlar
        )
        ihlal = secici.k.geometrik_ihlaller(p)
        print(f"{p.ad:<16}{p.tip:<12}{degerler}  {'uygun' if not ihlal else '; '.join(ihlal)}")
    print("\nBirimler: " + ", ".join(f"{k}: {v}" for k, v in OZELLIKLER.items() if k in sutunlar))


if __name__ == "__main__":
    sys.exit(main())
