"""Validierung und Vorschau hochgeladener Benutzer-CSV-Dateien."""

import csv
from io import StringIO
from typing import Any


TRENNZEICHEN_ANZEIGENAMEN = {
    ",": "Komma",
    ";": "Semikolon",
    "\t": "Tabulator",
    "|": "Senkrechter Strich",
}

MAPPING_KANDIDATEN = {
    "vorname": (
        "firstname",
        "givenname",
        "vorname",
    ),
    "nachname": (
        "lastname",
        "surname",
        "familyname",
        "nachname",
    ),
    "benutzername": (
        "username",
        "benutzername",
        "userprincipalname",
        "upn",
        "samaccountname",
        "login",
    ),
    "email": (
        "email",
        "emailaddress",
        "emailadresse",
        "mail",
    ),
    "abteilung": (
        "department",
        "division",
        "organizationalunit",
        "organisationseinheit",
        "abteilung",
    ),
}


class CsvImportFehler(ValueError):
    """Verstaendlicher Validierungsfehler einer CSV-Datei."""


def _spalten_normalisieren(spalten: list[str]) -> dict[str, str]:
    return {
        "".join(
            zeichen
            for zeichen in spalte.lower()
            if zeichen.isalnum()
        ): spalte
        for spalte in spalten
    }


def csv_mapping_vorschlagen(spalten: list[str]) -> dict[str, str]:
    """Ordnet uebliche deutsche und englische Spaltennamen automatisch zu."""
    normalisierte_spalten = _spalten_normalisieren(spalten)

    return {
        zielfeld: next(
            (
                normalisierte_spalten[kandidat]
                for kandidat in kandidaten
                if kandidat in normalisierte_spalten
            ),
            "",
        )
        for zielfeld, kandidaten in MAPPING_KANDIDATEN.items()
    }


def csv_datei_analysieren(dateiinhalt: bytes) -> dict[str, Any]:
    """Dekodiert, validiert und analysiert eine Benutzer-CSV-Datei.

    Die Funktion nimmt bewusst Bytes entgegen. Dadurch werden Kodierung,
    Trennzeichen, Kopfzeile und Zeilenstruktur an einer zentralen Stelle fuer
    neue und bereits eingerichtete CSV-Datenquellen gleich behandelt.
    """
    try:
        textinhalt = dateiinhalt.decode("utf-8-sig")
    except UnicodeDecodeError as fehler:
        raise CsvImportFehler(
            "Die Datei konnte nicht als UTF-8 gelesen werden."
        ) from fehler

    if not textinhalt.strip():
        raise CsvImportFehler("Die CSV-Datei ist leer.")

    try:
        dialekt = csv.Sniffer().sniff(
            textinhalt[:4096],
            delimiters=",;\t|",
        )
        reader = csv.DictReader(
            StringIO(textinhalt, newline=""),
            delimiter=dialekt.delimiter,
            quotechar='"',
            doublequote=True,
            strict=True,
        )

        spalten = [
            str(spalte or "").strip()
            for spalte in (reader.fieldnames or [])
            if str(spalte or "").strip()
        ]

        if not spalten:
            raise CsvImportFehler("Keine Kopfzeile erkannt.")

        datensaetze = []

        for zeile in reader:
            if (
                None in zeile
                or any(
                    "\n" in str(wert or "")
                    or "\r" in str(wert or "")
                    for wert in zeile.values()
                )
            ):
                raise CsvImportFehler(
                    "Mindestens eine CSV-Zeile ist beschädigt oder enthält "
                    "einen unerwarteten Zeilenumbruch."
                )

            bereinigte_zeile = {
                spalte: (
                    ""
                    if str(zeile.get(spalte) or "").strip() in {"-", "'-"}
                    else str(zeile.get(spalte) or "").strip()
                )
                for spalte in spalten
            }

            if any(bereinigte_zeile.values()):
                datensaetze.append(bereinigte_zeile)

    except csv.Error as fehler:
        raise CsvImportFehler(str(fehler)) from fehler

    return {
        "spalten": spalten,
        "datensaetze": datensaetze,
        "vorschau": datensaetze[:5],
        "tabellen_vorschau": [
            {
                "werte": [
                    zeile.get(spalte, "")
                    for spalte in spalten
                ]
            }
            for zeile in datensaetze[:5]
        ],
        "trennzeichen": dialekt.delimiter,
        "trennzeichen_anzeige": TRENNZEICHEN_ANZEIGENAMEN.get(
            dialekt.delimiter,
            dialekt.delimiter,
        ),
        "mapping": csv_mapping_vorschlagen(spalten),
    }
