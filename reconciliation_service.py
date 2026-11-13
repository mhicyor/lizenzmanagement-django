from demo.database import connect as demo_connection
import sqlite3
from typing import Any, Callable

from datenquelle_service import DATENBANK_DATEI


class ReconciliationFehler(Exception):
    """
    Verständlicher Fehler beim Abgleich externer
    Lizenzdatensätze mit der lokalen Datenbank.
    """


def lizenzdaten_abgleichen(
    *,
    datenquelle_id: int | str,
    datenquellen_schluessel: str,
    datensaetze: list[dict[str, Any]],
    beschreibung: str,
    anzahl_bereinigen: Callable[[Any], int],
    status_bereinigen: Callable[[Any], str],
) -> dict[str, Any]:
    """
    Übernimmt bereits normalisierte Datensätze einer
    externen Datenquelle in die Lizenzverwaltung.

    Eine externe Lizenz wird eindeutig über
    Datenquelle und externe ID erkannt.
    """
    try:
        datenquelle_id = int(
            datenquelle_id
        )
    except (TypeError, ValueError) as fehler:
        raise ReconciliationFehler(
            "Die Datenquellen-ID ist ungültig."
        ) from fehler

    datenquellen_schluessel = str(
        datenquellen_schluessel or ""
    ).strip()

    if not datenquellen_schluessel:
        raise ReconciliationFehler(
            "Der Datenquellen-Schlüssel fehlt."
        )

    angelegt = 0
    aktualisiert = 0
    deaktiviert = 0
    unveraendert = 0
    fehlerhaft = 0
    meldungen: list[dict[str, Any]] = []

    gelieferte_externe_ids = {
        str(
            datensatz.get("externe_id")
            or ""
        ).strip()
        for datensatz in datensaetze
        if (
            datensatz.get("aktion")
            != "fehlerhaft"
            and str(
                datensatz.get("externe_id")
                or ""
            ).strip()
        )
    }

    verbindung = demo_connection(DATENBANK_DATEI)
    verbindung.row_factory = sqlite3.Row

    try:
        for datensatz in datensaetze:
            aktion = str(
                datensatz.get("aktion")
                or ""
            ).strip().lower()

            externe_id = str(
                datensatz.get("externe_id")
                or ""
            ).strip()

            if aktion == "fehlerhaft":
                fehlerhaft += 1

                meldungen.append({
                    "externe_id": externe_id,
                    "aktion": "fehlerhaft",
                    "meldung": (
                        datensatz.get("meldung")
                        or "Der Datensatz ist ungültig."
                    ),
                })

                continue

            if aktion == "unveraendert":
                unveraendert += 1
                continue

            lizenzname = str(
                datensatz.get("lizenzname")
                or ""
            ).strip()

            anbieter = str(
                datensatz.get("anbieter")
                or ""
            ).strip()

            anzahl = anzahl_bereinigen(
                datensatz.get("anzahl")
            )

            status = status_bereinigen(
                datensatz.get("status")
            )

            verbrauch = datensatz.get("verbrauch")
            if verbrauch not in (None, ""):
                verbrauch = anzahl_bereinigen(verbrauch)
            else:
                verbrauch = None

            verbrauchsdatum = str(
                datensatz.get("verbrauchsdatum") or ""
            ).strip() or None
            startdatum = str(
                datensatz.get("startdatum") or ""
            ).strip() or None
            ablaufdatum = str(
                datensatz.get("ablaufdatum") or ""
            ).strip() or None
            produktschluessel = str(
                datensatz.get("produktschluessel") or ""
            ).strip() or None
            ziel_typ = str(
                datensatz.get("ziel_typ") or "benutzer"
            ).strip().lower()
            if ziel_typ not in {"benutzer", "geraet"}:
                ziel_typ = "benutzer"

            if not lizenzname or not externe_id:
                fehlerhaft += 1

                meldungen.append({
                    "externe_id": externe_id,
                    "aktion": "fehlerhaft",
                    "meldung": (
                        "Lizenzname oder externe ID fehlt."
                    ),
                })

                continue

            if aktion == "neu":
                verbindung.execute(
                    """
                    INSERT INTO lizenzen (
                        name,
                        anbieter,
                        beschreibung,
                        anzahl,
                        lizenztyp,
                        kosten,
                        lizenzklasse,
                        zuweisungsart,
                        kostenmodell,
                        technologiebereich,
                        datenquelle,
                        datenquelle_id,
                        api_sync_aktiv,
                        externe_id,
                        status,
                        externer_verbrauch,
                        verbrauch_gemeldet_am,
                        startdatum,
                        ablaufdatum,
                        externer_produktschluessel
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        lizenzname,
                        anbieter,
                        beschreibung,
                        anzahl,
                        lizenzname,
                        0,
                        ziel_typ,
                        ziel_typ,
                        "fortlaufend",
                        "allgemein",
                        datenquellen_schluessel,
                        datenquelle_id,
                        1,
                        externe_id,
                        status,
                        verbrauch,
                        verbrauchsdatum,
                        startdatum,
                        ablaufdatum,
                        produktschluessel,
                    ),
                )

                angelegt += 1
                continue

            if aktion == "aktualisieren":
                lizenz_id = datensatz.get(
                    "vorhandene_lizenz_id"
                )

                cursor = verbindung.execute(
                    """
                    UPDATE lizenzen
                    SET
                        name = ?,
                        anbieter = ?,
                        anzahl = ?,
                        lizenztyp = ?,
                        datenquelle = ?,
                        datenquelle_id = ?,
                        api_sync_aktiv = 1,
                        externe_id = ?,
                        status = ?,
                        externer_verbrauch = CASE
                            WHEN ? IS NULL THEN externer_verbrauch
                            ELSE ?
                        END,
                        verbrauch_gemeldet_am = CASE
                            WHEN ? IS NULL THEN verbrauch_gemeldet_am
                            ELSE ?
                        END,
                        startdatum = ?,
                        ablaufdatum = ?,
                        externer_produktschluessel = ?,
                        lizenzklasse = ?,
                        zuweisungsart = ?
                    WHERE id = ?
                      AND (
                          datenquelle_id = ?
                          OR (
                              datenquelle_id IS NULL
                              AND datenquelle = ?
                          )
                      )
                    """,
                    (
                        lizenzname,
                        anbieter,
                        anzahl,
                        lizenzname,
                        datenquellen_schluessel,
                        datenquelle_id,
                        externe_id,
                        status,
                        verbrauch,
                        verbrauch,
                        verbrauchsdatum,
                        verbrauchsdatum,
                        startdatum,
                        ablaufdatum,
                        produktschluessel,
                        ziel_typ,
                        ziel_typ,
                        lizenz_id,
                        datenquelle_id,
                        datenquellen_schluessel,
                    ),
                )

                if cursor.rowcount > 0:
                    aktualisiert += 1
                else:
                    fehlerhaft += 1

                    meldungen.append({
                        "externe_id": externe_id,
                        "aktion": "fehlerhaft",
                        "meldung": (
                            "Die vorhandene Lizenz konnte "
                            "nicht aktualisiert werden."
                        ),
                    })

        # Bei einer vollständig leeren Antwort wird
        # vorsichtshalber nichts massenhaft deaktiviert.
        if gelieferte_externe_ids:
            platzhalter = ", ".join(
                "?"
                for _ in gelieferte_externe_ids
            )

            parameter = [
                datenquelle_id,
                datenquellen_schluessel,
                *sorted(gelieferte_externe_ids),
            ]

            cursor = verbindung.execute(
                f"""
                UPDATE lizenzen
                SET
                    status = 'inaktiv',
                    api_sync_aktiv = 0
                WHERE (
                    datenquelle_id = ?
                    OR (
                        datenquelle_id IS NULL
                        AND datenquelle = ?
                    )
                )
                  AND externe_id IS NOT NULL
                  AND TRIM(externe_id) != ''
                  AND externe_id NOT IN (
                      {platzhalter}
                  )
                  AND (
                      status != 'inaktiv'
                      OR api_sync_aktiv != 0
                  )
                """,
                parameter,
            )

            deaktiviert = max(
                0,
                cursor.rowcount,
            )

        verbindung.commit()

    except Exception as fehler:
        verbindung.rollback()

        if isinstance(
            fehler,
            ReconciliationFehler,
        ):
            raise

        raise ReconciliationFehler(
            "Der Lizenzabgleich ist "
            "unerwartet fehlgeschlagen."
        ) from fehler

    finally:
        verbindung.close()

    return {
        "angelegt": angelegt,
        "aktualisiert": aktualisiert,
        "deaktiviert": deaktiviert,
        "unveraendert": unveraendert,
        "fehlerhaft": fehlerhaft,
        "meldungen": meldungen,
    }
