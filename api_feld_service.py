"""Generische Hilfen fuer verschachtelte REST-API-Daten.

Die Funktionen kennen keine Anbieter und keine konkreten Produktnamen. Sie
arbeiten ausschliesslich mit den im Assistenten gespeicherten Feldpfaden.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def werte_aus_pfad(daten: Any, feldpfad: str | None) -> list[Any]:
    """Liest einen Punktpfad und kann Listen mit ``[]`` auffaechern.

    Beispiele::

        product.name                 -> ["Produkt A"]
        usage.current.count          -> [12]
        assignedProducts[].code      -> ["A", "B"]

    Ein ``[]`` ist auch an Zwischenstufen moeglich. Leere oder nicht
    vorhandene Pfade liefern eine leere Liste statt einer Exception.
    """
    pfad = str(feldpfad or "").strip()
    if not pfad:
        return []

    aktuelle_werte = [daten]

    for roher_teil in pfad.split("."):
        ist_liste = roher_teil.endswith("[]")
        teil = roher_teil[:-2] if ist_liste else roher_teil
        naechste_werte: list[Any] = []

        for aktueller_wert in aktuelle_werte:
            if not isinstance(aktueller_wert, dict):
                continue

            wert = aktueller_wert.get(teil)

            if ist_liste:
                if isinstance(wert, list):
                    naechste_werte.extend(wert)
                elif wert is not None:
                    naechste_werte.append(wert)
            else:
                naechste_werte.append(wert)

        aktuelle_werte = naechste_werte

        if not aktuelle_werte:
            break

    ergebnis: list[Any] = []

    for wert in aktuelle_werte:
        if isinstance(wert, list):
            ergebnis.extend(wert)
        elif wert is not None:
            ergebnis.append(wert)

    return ergebnis


def wert_aus_pfad(daten: Any, feldpfad: str | None) -> Any:
    """Liest den ersten Wert eines Feldpfads.

    Bei einem expliziten Listenpfad wird die komplette Werteliste
    zurueckgegeben, damit Produktcodes und Gruppen nicht verloren gehen.
    """
    werte = werte_aus_pfad(daten, feldpfad)

    if not werte:
        return None

    if "[]" in str(feldpfad or ""):
        return werte

    return werte[0]


def blattpfade_ermitteln(daten: Any, praefix: str = "") -> set[str]:
    """Ermittelt auswählbare Blattpfade aus beliebig tiefem JSON."""
    pfade: set[str] = set()

    if isinstance(daten, dict):
        for schluessel, wert in daten.items():
            name = str(schluessel)
            pfad = f"{praefix}.{name}" if praefix else name

            if isinstance(wert, dict) and wert:
                pfade.update(blattpfade_ermitteln(wert, pfad))
            elif isinstance(wert, list) and wert:
                listenpfad = f"{pfad}[]"
                komplexe_werte = [
                    eintrag for eintrag in wert
                    if isinstance(eintrag, (dict, list))
                ]
                if komplexe_werte:
                    for eintrag in komplexe_werte[:3]:
                        pfade.update(
                            blattpfade_ermitteln(eintrag, listenpfad)
                        )
                else:
                    pfade.add(listenpfad)
            else:
                pfade.add(pfad)

    elif isinstance(daten, list):
        listenpfad = f"{praefix}[]" if praefix else "[]"
        for eintrag in daten[:3]:
            pfade.update(blattpfade_ermitteln(eintrag, listenpfad))

    elif praefix:
        pfade.add(praefix)

    return pfade


def eindeutige_textwerte(wert: Any) -> list[str]:
    """Normalisiert einen Einzelwert oder eine Liste ohne Duplikate."""
    if isinstance(wert, Iterable) and not isinstance(
        wert, (str, bytes, dict)
    ):
        rohwerte = list(wert)
    else:
        rohwerte = [wert]

    ergebnis: list[str] = []

    for rohwert in rohwerte:
        text = str(rohwert or "").strip()
        if text and text not in ergebnis:
            ergebnis.append(text)

    return ergebnis
