import sqlite3
from typing import Any

from datenquelle_service import DATENBANK_DATEI
from sqlite_context import sqlite_verbindung


class BenutzerMatchingFehler(Exception):
    """
    Verständlicher Fehler beim Abgleich eines externen
    Benutzers mit den lokalen beziehungsweise
    aus AD übernommenen Benutzerdaten.
    """


def _text(wert: Any) -> str:
    return str(
        wert or ""
    ).strip()


def _treffer_laden(
    *,
    feld: str,
    wert: str,
) -> list[dict[str, Any]]:
    erlaubte_felder = {
        "externe_id",
        "email",
        "benutzername",
    }

    if feld not in erlaubte_felder:
        raise BenutzerMatchingFehler(
            "Das Suchfeld ist ungültig."
        )

    wert = _text(
        wert
    )

    if not wert:
        return []

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeilen = verbindung.execute(
            f"""
            SELECT
                id,
                name,
                vorname,
                nachname,
                benutzername,
                email,
                abteilung,
                aktiv,
                quelle,
                externe_id
            FROM benutzer
            WHERE LOWER(
                TRIM(
                    COALESCE({feld}, '')
                )
            ) = LOWER(?)
            ORDER BY id
            LIMIT 2
            """,
            (wert,),
        ).fetchall()

    return [
        dict(zeile)
        for zeile in zeilen
    ]


def externen_benutzer_abgleichen(
    *,
    externe_id: Any = None,
    email: Any = None,
    benutzername: Any = None,
) -> dict[str, Any]:
    """
    Sucht einen externen Benutzer in einer festen,
    nachvollziehbaren Reihenfolge:

    1. externe ID
    2. E-Mail-Adresse
    3. Benutzername beziehungsweise UPN

    Es wird nichts gespeichert oder verändert.
    """
    benutzername_text = _text(benutzername)
    if "\\" in benutzername_text:
        benutzername_text = benutzername_text.rsplit("\\", 1)[-1]

    suchwerte = [
        (
            "externe_id",
            _text(externe_id),
            "externe_id",
        ),
        (
            "email",
            _text(email),
            "email",
        ),
        (
            "benutzername",
            benutzername_text,
            "benutzername",
        ),
    ]

    # Viele Systeme liefern den Anmeldenamen als UPN
    # (beispiel@firma.de), während AD lokal nur "beispiel" speichert.
    # Beide üblichen Schreibweisen werden deshalb nachvollziehbar geprüft.
    if "@" in benutzername_text:
        suchwerte.extend([
            (
                "email",
                benutzername_text,
                "benutzername",
            ),
            (
                "benutzername",
                benutzername_text.split("@", 1)[0],
                "benutzername",
            ),
        ])

    eindeutige_suchwerte = []
    bereits_geprueft: set[tuple[str, str]] = set()
    for feld, wert, bezeichnung in suchwerte:
        schluessel = (feld, wert.casefold())
        if not wert or schluessel in bereits_geprueft:
            continue
        bereits_geprueft.add(schluessel)
        eindeutige_suchwerte.append((feld, wert, bezeichnung))

    suchwerte = eindeutige_suchwerte

    verwendete_suchwerte = [
        bezeichnung
        for _, wert, bezeichnung in suchwerte
        if wert
    ]

    if not verwendete_suchwerte:
        return {
            "status": "keine_suchdaten",
            "benutzer": None,
            "trefferanzahl": 0,
            "gefunden_ueber": None,
            "meldung": (
                "Für den Benutzerabgleich fehlen "
                "externe ID, E-Mail-Adresse und "
                "Benutzername."
            ),
        }

    for feld, wert, bezeichnung in suchwerte:
        if not wert:
            continue

        treffer = _treffer_laden(
            feld=feld,
            wert=wert,
        )

        if len(treffer) == 1:
            return {
                "status": "gefunden",
                "benutzer": treffer[0],
                "trefferanzahl": 1,
                "gefunden_ueber": bezeichnung,
                "meldung": (
                    "Der externe Benutzer wurde "
                    f"eindeutig über {bezeichnung} "
                    "zugeordnet."
                ),
            }

        if len(treffer) > 1:
            return {
                "status": "mehrdeutig",
                "benutzer": None,
                "treffer": treffer,
                "trefferanzahl": len(treffer),
                "gefunden_ueber": bezeichnung,
                "meldung": (
                    "Für den externen Benutzer wurden "
                    f"mehrere Treffer über {bezeichnung} "
                    "gefunden."
                ),
            }

    return {
        "status": "nicht_gefunden",
        "benutzer": None,
        "trefferanzahl": 0,
        "gefunden_ueber": None,
        "meldung": (
            "Der externe Benutzer konnte keinem "
            "lokalen oder AD-Benutzer zugeordnet werden."
        ),
    }
