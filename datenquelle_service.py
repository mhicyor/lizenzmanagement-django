import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from crypto_service import entschluesseln, verschluesseln
from sqlite_context import sqlite_verbindung


PROJEKTVERZEICHNIS = Path(__file__).resolve().parent
DATENBANK_DATEI = PROJEKTVERZEICHNIS / "lizenzmanagement.db"

ERLAUBTE_AUTOMATISCHE_SYNC_INTERVALLE = {
    1440: "Täglich",
    10080: "Wöchentlich",
}


class DatenquelleFehler(Exception):
    """
    Verständlicher Fehler beim Speichern
    einer externen Datenquelle.
    """


def _text(wert: Any) -> str:
    return str(wert or "").strip()


def _mapping_pruefen(
    feld_mapping: dict[str, Any],
    mehrfachzuordnung_erlauben: bool = False,
) -> dict[str, str]:
    if not isinstance(feld_mapping, dict):
        raise DatenquelleFehler(
            "Die Feldzuordnung ist ungültig."
        )

    bereinigt = {
        str(schluessel).strip(): _text(wert)
        for schluessel, wert in feld_mapping.items()
        if _text(wert)
    }

    if not bereinigt.get("lizenzname"):
        raise DatenquelleFehler(
            "Bitte ein API-Feld für den "
            "Lizenznamen zuordnen."
        )

    erlaubte_felder = {
        "lizenzname",
        "externe_id",
        "anbieter",
        "anzahl",
        "verbrauch",
        "verbrauchsdatum",
        "startdatum",
        "status",
        "email",
        "ablaufdatum",
        "produktschluessel",
        "ziel_typ_feld",
        "ziel_typ_standard",
        "ziel_typ_benutzer_werte",
        "ziel_typ_geraete_werte",
    }

    unbekannte_felder = (
        set(bereinigt) - erlaubte_felder
    )

    if unbekannte_felder:
        raise DatenquelleFehler(
            "Die Feldzuordnung enthält "
            "unbekannte interne Felder."
        )

    konfigurationsfelder = {
        "ziel_typ_feld",
        "ziel_typ_standard",
        "ziel_typ_benutzer_werte",
        "ziel_typ_geraete_werte",
    }
    zugeordnete_api_felder = [
        wert
        for schluessel, wert in bereinigt.items()
        if schluessel not in konfigurationsfelder
    ]

    if (
        not mehrfachzuordnung_erlauben
        and len(zugeordnete_api_felder) != len(
            set(zugeordnete_api_felder)
        )
    ):
        raise DatenquelleFehler(
            "Ein API-Feld darf nicht mehrfach "
            "zugeordnet werden."
        )

    return bereinigt


def _csv_benutzer_mapping_pruefen(
    feld_mapping: dict[str, Any],
) -> dict[str, str]:
    """Prüft die Feldzuordnung einer Benutzer-CSV."""
    if not isinstance(feld_mapping, dict):
        raise DatenquelleFehler(
            "Die Feldzuordnung ist ungültig."
        )

    bereinigt = {
        str(schluessel).strip(): _text(wert)
        for schluessel, wert in feld_mapping.items()
        if _text(wert)
    }

    erlaubte_felder = {
        "name",
        "vorname",
        "nachname",
        "benutzername",
        "email",
        "abteilung",
        "externe_id",
        "status",
    }

    if set(bereinigt) - erlaubte_felder:
        raise DatenquelleFehler(
            "Die Feldzuordnung enthält unbekannte "
            "Benutzerfelder."
        )

    if not (
        bereinigt.get("name")
        or (
            bereinigt.get("vorname")
            and bereinigt.get("nachname")
        )
    ):
        raise DatenquelleFehler(
            "Bitte Vorname und Nachname zuordnen."
        )

    zugeordnete_spalten = list(bereinigt.values())

    if len(zugeordnete_spalten) != len(
        set(zugeordnete_spalten)
    ):
        raise DatenquelleFehler(
            "Eine CSV-Spalte darf nicht mehrfach "
            "zugeordnet werden."
        )

    return bereinigt


def alte_csv_temp_dateien_bereinigen(
    max_alter_stunden: int = 24,
) -> int:
    """
    Entfernt veraltete temporäre CSV-Dateien.

    Es werden ausschließlich CSV-Dateien innerhalb von
    media/csv_datenquellen/temp berücksichtigt.
    """
    try:
        max_alter_stunden = max(
            1,
            int(max_alter_stunden),
        )
    except (TypeError, ValueError):
        max_alter_stunden = 24

    temp_verzeichnis = (
        PROJEKTVERZEICHNIS
        / "media"
        / "csv_datenquellen"
        / "temp"
    ).resolve()

    if not temp_verzeichnis.is_dir():
        return 0

    grenzzeitpunkt = (
        datetime.now(timezone.utc).timestamp()
        - max_alter_stunden * 60 * 60
    )

    geloescht = 0

    for dateipfad in temp_verzeichnis.glob("*.csv"):
        try:
            sicherer_pfad = dateipfad.resolve()

            sicherer_pfad.relative_to(
                temp_verzeichnis
            )

            if (
                sicherer_pfad.is_file()
                and sicherer_pfad.stat().st_mtime
                < grenzzeitpunkt
            ):
                sicherer_pfad.unlink()
                geloescht += 1

        except (
            OSError,
            ValueError,
        ):
            continue

    return geloescht


def csv_datenquelle_speichern(
    name: str,
    dateiname: str,
    dateipfad: str,
    trennzeichen: str,
    feld_mapping: dict[str, Any],
    datensatzanzahl: int = 0,
) -> int:
    """
    Speichert die Metadaten einer CSV-Datenquelle.

    Die eigentliche CSV-Datei muss zuvor dauerhaft
    im lokalen Medienverzeichnis abgelegt worden sein.
    """
    name = _text(name)
    dateiname = _text(dateiname)
    dateipfad = _text(dateipfad)
    trennzeichen = _text(trennzeichen)

    if not name:
        raise DatenquelleFehler(
            "Der Name der CSV-Datenquelle fehlt."
        )

    if not dateiname:
        raise DatenquelleFehler(
            "Der ursprüngliche CSV-Dateiname fehlt."
        )

    if not dateipfad:
        raise DatenquelleFehler(
            "Der Speicherpfad der CSV-Datei fehlt."
        )

    if trennzeichen not in {",", ";", "\\t", "|"}:
        raise DatenquelleFehler(
            "Das erkannte CSV-Trennzeichen ist ungültig."
        )

    try:
        datensatzanzahl = max(
            0,
            int(datensatzanzahl),
        )
    except (TypeError, ValueError):
        datensatzanzahl = 0

    mapping = _csv_benutzer_mapping_pruefen(
        feld_mapping
    )

    mapping_json = json.dumps(
        mapping,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    konfiguration_info = json.dumps(
        {
            "dateiname": dateiname,
            "trennzeichen": trennzeichen,
            "encoding": "utf-8-sig",
            "datensatzanzahl": datensatzanzahl,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        cursor = verbindung.cursor()

        vorhanden = cursor.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE LOWER(name) = LOWER(?)
              AND aktiv = 1
            LIMIT 1
            """,
            (name,),
        ).fetchone()

        if vorhanden:
            raise DatenquelleFehler(
                "Eine aktive Datenquelle mit "
                "diesem Namen existiert bereits."
            )

        cursor.execute(
            """
            INSERT INTO datenquellen (
                name,
                typ,
                status,
                aktiv,
                auth_typ,
                demo_modus,
                endpunkt,
                feld_mapping,
                konfiguration_info,
                letzter_test,
                letzte_meldung,
                erstellt_am,
                aktualisiert_am
            )
            VALUES (
                ?,
                'csv',
                'verbunden',
                1,
                'datei',
                0,
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP,
                ?,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """,
            (
                name,
                dateipfad,
                mapping_json,
                konfiguration_info,
                (
                    f"CSV-Datei erkannt: "
                    f"{datensatzanzahl} Datensätze."
                ),
            ),
        )

        datenquelle_id = cursor.lastrowid
        verbindung.commit()

    return int(datenquelle_id)


def csv_datenquelle_aktualisieren(
    datenquelle_id: int | str,
    name: str,
    dateiname: str,
    dateipfad: str,
    trennzeichen: str,
    feld_mapping: dict[str, Any],
    datensatzanzahl: int = 0,
) -> bool:
    """
    Aktualisiert eine bestehende CSV-Datenquelle.

    Die Datenquellen-ID bleibt erhalten. Dateipfad,
    Mapping und CSV-Metadaten werden ersetzt.
    """
    try:
        datenquelle_id = int(
            datenquelle_id
        )
    except (TypeError, ValueError) as fehler:
        raise DatenquelleFehler(
            "Die Datenquellen-ID ist ungültig."
        ) from fehler

    name = _text(name)
    dateiname = _text(dateiname)
    dateipfad = _text(dateipfad)
    trennzeichen = _text(trennzeichen)

    if not name:
        raise DatenquelleFehler(
            "Der Name der CSV-Datenquelle fehlt."
        )

    if not dateiname:
        raise DatenquelleFehler(
            "Der ursprüngliche CSV-Dateiname fehlt."
        )

    if not dateipfad:
        raise DatenquelleFehler(
            "Der Speicherpfad der CSV-Datei fehlt."
        )

    if trennzeichen not in {",", ";", "\\t", "|"}:
        raise DatenquelleFehler(
            "Das erkannte CSV-Trennzeichen ist ungültig."
        )

    try:
        datensatzanzahl = max(
            0,
            int(datensatzanzahl),
        )
    except (TypeError, ValueError):
        datensatzanzahl = 0

    mapping = _csv_benutzer_mapping_pruefen(
        feld_mapping
    )

    mapping_json = json.dumps(
        mapping,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    konfiguration_info = json.dumps(
        {
            "dateiname": dateiname,
            "trennzeichen": trennzeichen,
            "encoding": "utf-8-sig",
            "datensatzanzahl": datensatzanzahl,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        cursor = verbindung.cursor()

        vorhanden = cursor.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE id = ?
              AND LOWER(typ) = 'csv'
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

        if vorhanden is None:
            raise DatenquelleFehler(
                "Die CSV-Datenquelle wurde nicht gefunden."
            )

        namenskonflikt = cursor.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE LOWER(name) = LOWER(?)
              AND id != ?
              AND aktiv = 1
            LIMIT 1
            """,
            (
                name,
                datenquelle_id,
            ),
        ).fetchone()

        if namenskonflikt:
            raise DatenquelleFehler(
                "Eine andere aktive Datenquelle mit "
                "diesem Namen existiert bereits."
            )

        cursor.execute(
            """
            UPDATE datenquellen
            SET
                name = ?,
                status = 'verbunden',
                aktiv = 1,
                auth_typ = 'datei',
                endpunkt = ?,
                feld_mapping = ?,
                konfiguration_info = ?,
                letzter_test = CURRENT_TIMESTAMP,
                letzte_meldung = ?,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE id = ?
              AND LOWER(typ) = 'csv'
            """,
            (
                name,
                dateipfad,
                mapping_json,
                konfiguration_info,
                (
                    f"CSV-Datei aktualisiert: "
                    f"{datensatzanzahl} Datensätze."
                ),
                datenquelle_id,
            ),
        )

        aktualisiert = (
            cursor.rowcount > 0
        )

        verbindung.commit()

    return aktualisiert


def rest_datenquelle_speichern(
    konfiguration: dict[str, Any],
    feld_mapping: dict[str, Any],
    zuweisungen_feld_mapping: (
        dict[str, Any] | None
    ) = None,
) -> int:
    name = _text(
        konfiguration.get("name")
    )

    basis_url = _text(
        konfiguration.get("basis_url")
    )

    endpunkt = _text(
        konfiguration.get("endpunkt")
    )

    zuweisungen_endpunkt = _text(
        konfiguration.get(
            "zuweisungen_endpunkt"
        )
    )

    auth_typ = _text(
        konfiguration.get("auth_typ")
    )

    token_url = _text(
        konfiguration.get("token_url")
    )

    scope = _text(
        konfiguration.get("scope")
    )

    rest_datenart = _text(
        konfiguration.get("rest_datenart")
    ) or "lizenzbestand"

    if rest_datenart not in {
        "lizenzbestand",
        "benutzer_gruppen",
        "benutzer_lizenz",
    }:
        rest_datenart = "lizenzbestand"

    if not name:
        raise DatenquelleFehler(
            "Der Name der Verbindung fehlt."
        )

    if not basis_url:
        raise DatenquelleFehler(
            "Die Basis-URL fehlt."
        )

    mapping = _mapping_pruefen(
        feld_mapping,
        mehrfachzuordnung_erlauben=(
            rest_datenart in {
                "benutzer_gruppen",
                "benutzer_lizenz",
            }
        ),
    )

    if zuweisungen_feld_mapping is None:
        zuweisungen_mapping = {}
    elif not isinstance(
        zuweisungen_feld_mapping,
        dict,
    ):
        raise DatenquelleFehler(
            "Die Feldzuordnung für Zuweisungen "
            "ist ungültig."
        )
    else:
        zuweisungen_mapping = {
            str(schluessel).strip(): _text(wert)
            for schluessel, wert
            in zuweisungen_feld_mapping.items()
            if _text(wert)
        }

    geheime_daten = {
        "api_key_header": _text(
            konfiguration.get(
                "api_key_header"
            )
        ),
        "api_key": str(
            konfiguration.get(
                "api_key",
                "",
            )
        ),
        "api_key_id": _text(
            konfiguration.get(
                "api_key_id"
            )
        ),
        "basic_benutzername": _text(
            konfiguration.get(
                "basic_benutzername"
            )
        ),
        "basic_passwort": str(
            konfiguration.get(
                "basic_passwort",
                "",
            )
        ),
        "bearer_token": str(
            konfiguration.get(
                "bearer_token",
                "",
            )
        ),
        "client_id": _text(
            konfiguration.get(
                "client_id"
            )
        ),
        "client_secret": str(
            konfiguration.get(
                "client_secret",
                "",
            )
        ),
        "zusaetzliche_header": (
            konfiguration.get(
                "zusaetzliche_header",
                [],
            )
        ),
    }

    auth_daten_verschluesselt = (
        verschluesseln(
            geheime_daten
        )
    )

    mapping_json = json.dumps(
        mapping,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    zuweisungen_mapping_json = json.dumps(
        zuweisungen_mapping,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        cursor = verbindung.cursor()

        vorhanden = cursor.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE LOWER(name) = LOWER(?)
              AND aktiv = 1
            LIMIT 1
            """,
            (name,),
        ).fetchone()

        if vorhanden:
            raise DatenquelleFehler(
                "Eine aktive Datenquelle mit "
                "diesem Namen existiert bereits."
            )

        cursor.execute(
            """
            INSERT INTO datenquellen (
                name,
                typ,
                status,
                aktiv,
                auth_typ,
                demo_modus,
                basis_url,
                endpunkt,
                zuweisungen_endpunkt,
                token_url,
                scope,
                feld_mapping,
                zuweisungen_feld_mapping,
                rest_datenart,
                auth_daten_verschluesselt,
                letzter_test,
                letzte_meldung,
                erstellt_am,
                aktualisiert_am
            )
            VALUES (
                ?,
                'rest_api',
                'verbunden',
                1,
                ?,
                0,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP,
                ?,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """,
            (
                name,
                auth_typ,
                basis_url,
                endpunkt,
                zuweisungen_endpunkt,
                token_url,
                scope,
                mapping_json,
                zuweisungen_mapping_json,
                rest_datenart,
                auth_daten_verschluesselt,
                (
                    "Verbindung erfolgreich "
                    "getestet und gespeichert."
                ),
            ),
        )

        datenquelle_id = cursor.lastrowid
        verbindung.commit()

    return int(datenquelle_id)



def rest_datenquelle_aktualisieren(
    datenquelle_id: int | str,
    konfiguration: dict[str, Any],
    feld_mapping: dict[str, Any],
    zuweisungen_feld_mapping: (
        dict[str, Any] | None
    ) = None,
) -> bool:
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError) as fehler:
        raise DatenquelleFehler(
            "Die Datenquelle ist ungültig."
        ) from fehler

    name = _text(
        konfiguration.get("name")
    )
    basis_url = _text(
        konfiguration.get("basis_url")
    )
    endpunkt = _text(
        konfiguration.get("endpunkt")
    )
    zuweisungen_endpunkt = _text(
        konfiguration.get(
            "zuweisungen_endpunkt"
        )
    )
    auth_typ = _text(
        konfiguration.get("auth_typ")
    )
    token_url = _text(
        konfiguration.get("token_url")
    )
    scope = _text(
        konfiguration.get("scope")
    )

    rest_datenart = _text(
        konfiguration.get("rest_datenart")
    ) or "lizenzbestand"

    if rest_datenart not in {
        "lizenzbestand",
        "benutzer_gruppen",
        "benutzer_lizenz",
    }:
        rest_datenart = "lizenzbestand"

    if not name:
        raise DatenquelleFehler(
            "Der Name der Verbindung fehlt."
        )

    if not basis_url:
        raise DatenquelleFehler(
            "Die Basis-URL fehlt."
        )

    mapping = _mapping_pruefen(
        feld_mapping,
        mehrfachzuordnung_erlauben=(
            rest_datenart in {
                "benutzer_gruppen",
                "benutzer_lizenz",
            }
        ),
    )

    if zuweisungen_feld_mapping is None:
        zuweisungen_mapping = {}
    elif not isinstance(
        zuweisungen_feld_mapping,
        dict,
    ):
        raise DatenquelleFehler(
            "Die Feldzuordnung für Zuweisungen "
            "ist ungültig."
        )
    else:
        zuweisungen_mapping = {
            str(schluessel).strip(): _text(wert)
            for schluessel, wert
            in zuweisungen_feld_mapping.items()
            if _text(wert)
        }

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        vorhanden = verbindung.execute(
            """
            SELECT
                id,
                typ,
                auth_daten_verschluesselt
            FROM datenquellen
            WHERE id = ?
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

        if vorhanden is None:
            raise DatenquelleFehler(
                "Die Datenquelle wurde nicht gefunden."
            )

        if _text(vorhanden["typ"]).lower() != "rest_api":
            raise DatenquelleFehler(
                "Nur REST-API-Verbindungen können "
                "hier bearbeitet werden."
            )

        namenskonflikt = verbindung.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE LOWER(name) = LOWER(?)
              AND id != ?
              AND aktiv = 1
            LIMIT 1
            """,
            (
                name,
                datenquelle_id,
            ),
        ).fetchone()

        if namenskonflikt:
            raise DatenquelleFehler(
                "Eine andere aktive Datenquelle mit "
                "diesem Namen existiert bereits."
            )

        bisherige_geheimnisse = entschluesseln(
            vorhanden[
                "auth_daten_verschluesselt"
            ]
        )

        neue_geheimnisse = {
            "api_key_header": _text(
                konfiguration.get(
                    "api_key_header"
                )
            ),
            "api_key": str(
                konfiguration.get(
                    "api_key",
                    "",
                )
            ),
            "api_key_id": _text(
                konfiguration.get(
                    "api_key_id"
                )
            ),
            "basic_benutzername": _text(
                konfiguration.get(
                    "basic_benutzername"
                )
            ),
            "basic_passwort": str(
                konfiguration.get(
                    "basic_passwort",
                    "",
                )
            ),
            "bearer_token": str(
                konfiguration.get(
                    "bearer_token",
                    "",
                )
            ),
            "client_id": _text(
                konfiguration.get(
                    "client_id"
                )
            ),
            "client_secret": str(
                konfiguration.get(
                    "client_secret",
                    "",
                )
            ),
            "zusaetzliche_header": (
                konfiguration.get(
                    "zusaetzliche_header",
                    [],
                )
            ),
        }

        for schluessel in (
            "api_key",
            "basic_passwort",
            "bearer_token",
            "client_secret",
        ):
            if not neue_geheimnisse[schluessel]:
                neue_geheimnisse[schluessel] = (
                    bisherige_geheimnisse.get(
                        schluessel,
                        "",
                    )
                )

        for schluessel in (
            "api_key_header",
            "api_key_id",
            "basic_benutzername",
            "client_id",
        ):
            if not neue_geheimnisse[schluessel]:
                neue_geheimnisse[schluessel] = (
                    bisherige_geheimnisse.get(
                        schluessel,
                        "",
                    )
                )

        if not neue_geheimnisse[
            "zusaetzliche_header"
        ]:
            neue_geheimnisse[
                "zusaetzliche_header"
            ] = bisherige_geheimnisse.get(
                "zusaetzliche_header",
                [],
            )

        mapping_json = json.dumps(
            mapping,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        zuweisungen_mapping_json = json.dumps(
            zuweisungen_mapping,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        geheimnisse_verschluesselt = (
            verschluesseln(
                neue_geheimnisse
            )
        )

        cursor = verbindung.execute(
            """
            UPDATE datenquellen
            SET
                name = ?,
                status = 'verbunden',
                auth_typ = ?,
                basis_url = ?,
                endpunkt = ?,
                zuweisungen_endpunkt = ?,
                token_url = ?,
                scope = ?,
                feld_mapping = ?,
                zuweisungen_feld_mapping = ?,
                rest_datenart = ?,
                auth_daten_verschluesselt = ?,
                letzter_test = CURRENT_TIMESTAMP,
                letzte_meldung = ?,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                name,
                auth_typ,
                basis_url,
                endpunkt,
                zuweisungen_endpunkt,
                token_url,
                scope,
                mapping_json,
                zuweisungen_mapping_json,
                rest_datenart,
                geheimnisse_verschluesselt,
                (
                    "Verbindung erfolgreich getestet "
                    "und aktualisiert."
                ),
                datenquelle_id,
            ),
        )

        verbindung.commit()

    return cursor.rowcount > 0



def _zeile_als_dict(
    zeile: sqlite3.Row | None,
) -> dict[str, Any] | None:
    if zeile is None:
        return None

    return dict(zeile)


def naechste_automatische_synchronisation_planen(
    datenquelle_id: int | str,
) -> str | None:
    """
    Plant ausgehend vom aktuellen UTC-Zeitpunkt
    den nächsten automatischen Lauf.
    """
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError) as fehler:
        raise DatenquelleFehler(
            "Die Datenquelle ist ungültig."
        ) from fehler

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        datenquelle = verbindung.execute(
            """
            SELECT
                automatische_synchronisation,
                sync_intervall_minuten
            FROM datenquellen
            WHERE id = ?
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

        if datenquelle is None:
            raise DatenquelleFehler(
                "Die Datenquelle wurde nicht gefunden."
            )

        aktiviert = bool(
            datenquelle[
                "automatische_synchronisation"
            ]
        )

        intervall_minuten = datenquelle[
            "sync_intervall_minuten"
        ]

        if not aktiviert or intervall_minuten is None:
            verbindung.execute(
                """
                UPDATE datenquellen
                SET
                    naechste_synchronisation = NULL,
                    aktualisiert_am = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (datenquelle_id,),
            )

            verbindung.commit()
            return None

        try:
            intervall_minuten = int(
                intervall_minuten
            )
        except (TypeError, ValueError) as fehler:
            raise DatenquelleFehler(
                "Das gespeicherte "
                "Synchronisationsintervall ist ungültig."
            ) from fehler

        if intervall_minuten < 1:
            raise DatenquelleFehler(
                "Das gespeicherte "
                "Synchronisationsintervall ist ungültig."
            )

        naechster_zeitpunkt = (
            datetime.now(timezone.utc)
            + timedelta(
                minutes=intervall_minuten
            )
        ).strftime("%Y-%m-%d %H:%M:%S")

        verbindung.execute(
            """
            UPDATE datenquellen
            SET
                naechste_synchronisation = ?,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                naechster_zeitpunkt,
                datenquelle_id,
            ),
        )

        verbindung.commit()

    return naechster_zeitpunkt


def faellige_automatische_datenquellen_laden(
) -> list[dict[str, Any]]:
    """
    Lädt alle aktiven Datenquellen, deren automatisch
    geplanter Synchronisationszeitpunkt erreicht ist.
    """
    jetzt = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeilen = verbindung.execute(
            """
            SELECT
                id,
                name,
                typ,
                status,
                aktiv,
                automatische_synchronisation,
                sync_intervall_minuten,
                naechste_synchronisation
            FROM datenquellen
            WHERE aktiv = 1
              AND automatische_synchronisation = 1
              AND sync_intervall_minuten IS NOT NULL
              AND naechste_synchronisation IS NOT NULL
              AND naechste_synchronisation <= ?
            ORDER BY naechste_synchronisation ASC, id ASC
            """,
            (jetzt,),
        ).fetchall()

    return [
        dict(zeile)
        for zeile in zeilen
    ]


def automatische_synchronisation_speichern(
    datenquelle_id: int | str,
    aktiviert: bool,
    intervall_minuten: int | str | None = None,
) -> dict[str, Any]:
    """
    Speichert die Zeitplanung einer Datenquelle.

    Beim Aktivieren wird der nächste geplante Lauf
    ausgehend vom aktuellen UTC-Zeitpunkt berechnet.
    """
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError) as fehler:
        raise DatenquelleFehler(
            "Die Datenquelle ist ungültig."
        ) from fehler

    aktiviert = bool(aktiviert)

    if aktiviert:
        try:
            intervall_minuten = int(
                intervall_minuten
            )
        except (TypeError, ValueError) as fehler:
            raise DatenquelleFehler(
                "Bitte ein gültiges "
                "Synchronisationsintervall angeben."
            ) from fehler

        if (
            intervall_minuten
            not in ERLAUBTE_AUTOMATISCHE_SYNC_INTERVALLE
        ):
            raise DatenquelleFehler(
                "Bitte täglich oder wöchentlich als "
                "Häufigkeit auswählen."
            )

        naechste_synchronisation = (
            datetime.now(timezone.utc)
            + timedelta(
                minutes=intervall_minuten
            )
        ).strftime("%Y-%m-%d %H:%M:%S")

    else:
        intervall_minuten = None
        naechste_synchronisation = None

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        vorhanden = verbindung.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE id = ?
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

        if vorhanden is None:
            raise DatenquelleFehler(
                "Die Datenquelle wurde nicht gefunden."
            )

        verbindung.execute(
            """
            UPDATE datenquellen
            SET
                automatische_synchronisation = ?,
                sync_intervall_minuten = ?,
                naechste_synchronisation = ?,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                1 if aktiviert else 0,
                intervall_minuten,
                naechste_synchronisation,
                datenquelle_id,
            ),
        )

        verbindung.commit()

    datenquelle = datenquelle_laden(
        datenquelle_id
    )

    if datenquelle is None:
        raise DatenquelleFehler(
            "Die gespeicherte Datenquelle konnte "
            "nicht erneut geladen werden."
        )

    return datenquelle


def datenquelle_laden(
    datenquelle_id: int | str,
) -> dict[str, Any] | None:
    """
    Lädt genau eine Datenquelle anhand ihrer ID.

    Verschlüsselte Zugangsdaten werden dabei bewusst
    nicht entschlüsselt und nicht zurückgegeben.
    """
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError):
        return None

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeile = verbindung.execute(
            """
            SELECT
                id,
                name,
                typ,
                status,
                aktiv,
                letzter_test,
                letzte_meldung,
                erstellt_am,
                aktualisiert_am,
                auth_typ,
                demo_modus,
                konfiguration_info,
                basis_url,
                endpunkt,
                zuweisungen_endpunkt,
                token_url,
                scope,
                feld_mapping,
                zuweisungen_feld_mapping,
                rest_datenart,
                automatische_synchronisation,
                sync_intervall_minuten,
                naechste_synchronisation
            FROM datenquellen
            WHERE id = ?
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

    return _zeile_als_dict(zeile)


def datenquelle_mit_geheimnissen_laden(
    datenquelle_id: int | str,
) -> dict[str, Any] | None:
    """
    Lädt eine Datenquelle einschließlich der serverseitig
    entschlüsselten Zugangsdaten.

    Diese Funktion darf nur innerhalb vertrauenswürdiger
    Service- und View-Logik verwendet werden. Die zurück-
    gegebenen Geheimnisse dürfen niemals an Templates oder
    API-Antworten weitergereicht werden.
    """
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError):
        return None

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeile = verbindung.execute(
            """
            SELECT
                id,
                name,
                typ,
                auth_typ,
                basis_url,
                endpunkt,
                token_url,
                scope,
                feld_mapping,
                zuweisungen_feld_mapping,
                rest_datenart,
                auth_daten_verschluesselt
            FROM datenquellen
            WHERE id = ?
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

    if zeile is None:
        return None

    ergebnis = dict(zeile)

    ergebnis["geheimnisse"] = entschluesseln(
        ergebnis.pop(
            "auth_daten_verschluesselt"
        )
    )

    return ergebnis

def datenquelle_deaktivieren(
    datenquelle_id: int | str,
) -> bool:
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError):
        return False

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        cursor = verbindung.execute(
            """
            UPDATE datenquellen
            SET
                aktiv = 0,
                status = 'deaktiviert',
                letzte_meldung = ?,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                "Die Datenquelle wurde deaktiviert.",
                datenquelle_id,
            ),
        )

        verbindung.commit()

    return cursor.rowcount > 0


def datenquelle_reaktivieren(
    datenquelle_id: int | str,
) -> bool:
    try:
        datenquelle_id = int(datenquelle_id)
    except (TypeError, ValueError):
        return False

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        cursor = verbindung.execute(
            """
            UPDATE datenquellen
            SET
                aktiv = 1,
                status = 'verbunden',
                letzte_meldung = ?,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                "Die Datenquelle wurde reaktiviert.",
                datenquelle_id,
            ),
        )

        verbindung.commit()

    return cursor.rowcount > 0


def datenquelle_loeschen(
    datenquelle_id: int | str,
) -> bool:
    """
    Löscht eine Datenquelle.

    Bei CSV-Datenquellen wird nach erfolgreichem
    Datenbank-Löschen zusätzlich die zugehörige Datei
    aus dem geschützten CSV-Medienverzeichnis entfernt.
    """
    try:
        datenquelle_id = int(
            datenquelle_id
        )
    except (TypeError, ValueError):
        return False

    typ = ""
    gespeicherter_dateipfad = ""

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        datenquelle = verbindung.execute(
            """
            SELECT
                typ,
                endpunkt
            FROM datenquellen
            WHERE id = ?
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

        if datenquelle is None:
            return False

        typ = _text(
            datenquelle["typ"]
        ).lower()

        gespeicherter_dateipfad = _text(
            datenquelle["endpunkt"]
        )

        cursor = verbindung.execute(
            """
            DELETE FROM datenquellen
            WHERE id = ?
            """,
            (datenquelle_id,),
        )

        geloescht = (
            cursor.rowcount > 0
        )

        verbindung.commit()

    if (
        geloescht
        and typ == "csv"
        and gespeicherter_dateipfad
    ):
        csv_verzeichnis = (
            PROJEKTVERZEICHNIS
            / "media"
            / "csv_datenquellen"
        ).resolve()

        dateipfad = (
            PROJEKTVERZEICHNIS
            / "media"
            / gespeicherter_dateipfad
        ).resolve()

        try:
            dateipfad.relative_to(
                csv_verzeichnis
            )
        except ValueError:
            # Aus Sicherheitsgründen niemals Dateien
            # außerhalb des CSV-Verzeichnisses löschen.
            pass
        else:
            try:
                if (
                    dateipfad.is_file()
                    and dateipfad.suffix.lower()
                    == ".csv"
                ):
                    dateipfad.unlink()
            except OSError:
                # Der Datenbankeintrag ist bereits gelöscht.
                # Ein Dateisystemfehler soll diesen Vorgang
                # nicht nachträglich als fehlgeschlagen melden.
                pass

    return geloescht



def lade_eingerichtete_datenquellen(
    nur_aktive: bool = True,
) -> list[dict[str, Any]]:
    """
    Lädt die eingerichteten Datenquellen für Auswahlfelder,
    Übersichten und Lizenzdetails.

    Zugangsdaten bleiben verschlüsselt und werden nicht
    an Views oder Templates weitergegeben.
    """
    sql = """
        SELECT
            id,
            name,
            typ,
            status,
            aktiv,
            letzter_test,
            letzte_meldung,
            erstellt_am,
            aktualisiert_am,
            auth_typ,
            demo_modus,
            konfiguration_info,
            basis_url,
            endpunkt,
            zuweisungen_endpunkt,
            token_url,
            scope,
            feld_mapping,
            zuweisungen_feld_mapping,
            automatische_synchronisation,
            sync_intervall_minuten,
            naechste_synchronisation
        FROM datenquellen
    """

    parameter: tuple[Any, ...] = ()

    if nur_aktive:
        sql += " WHERE aktiv = ?"
        parameter = (1,)

    sql += """
        ORDER BY
            CASE
                WHEN LOWER(typ) = 'adobe' THEN 0
                ELSE 1
            END,
            LOWER(name),
            id
    """

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeilen = verbindung.execute(
            sql,
            parameter,
        ).fetchall()

    return [
        dict(zeile)
        for zeile in zeilen
    ]


def datenquelle_speichern(
    name: str,
    typ: str,
    status: str = "nicht_eingerichtet",
    auth_typ: str = "",
    demo_modus: bool = False,
    letzte_meldung: str = "",
) -> int:
    """
    Einfache Kompatibilitätsfunktion für bestehende
    anbieterbezogene Datenquellen.

    Für neue generische REST-APIs muss stattdessen
    rest_datenquelle_speichern() verwendet werden.
    """
    name = _text(name)
    typ = _text(typ).lower()
    status = (
        _text(status)
        or "nicht_eingerichtet"
    )
    auth_typ = _text(auth_typ)
    letzte_meldung = _text(
        letzte_meldung
    )

    if not name:
        raise DatenquelleFehler(
            "Der Name der Datenquelle fehlt."
        )

    if not typ:
        raise DatenquelleFehler(
            "Der Typ der Datenquelle fehlt."
        )

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        cursor = verbindung.cursor()

        vorhanden = cursor.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE LOWER(name) = LOWER(?)
              AND LOWER(typ) = LOWER(?)
              AND aktiv = 1
            LIMIT 1
            """,
            (
                name,
                typ,
            ),
        ).fetchone()

        if vorhanden:
            raise DatenquelleFehler(
                "Diese Datenquelle ist bereits eingerichtet."
            )

        cursor.execute(
            """
            INSERT INTO datenquellen (
                name,
                typ,
                status,
                aktiv,
                auth_typ,
                demo_modus,
                letzte_meldung,
                erstellt_am,
                aktualisiert_am
            )
            VALUES (
                ?,
                ?,
                ?,
                1,
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """,
            (
                name,
                typ,
                status,
                auth_typ,
                int(bool(demo_modus)),
                letzte_meldung,
            ),
        )

        datenquelle_id = cursor.lastrowid
        verbindung.commit()

    return int(datenquelle_id)


def demo_datenquelle_anlegen(
    name: str = "Testverbindung",
    typ: str = "rest_api",
    auth_typ: str = "keine",
) -> int:
    """
    Alte Kompatibilitätsfunktion für lokale Testdaten.

    Sie wird aktuell nicht von der Oberfläche verwendet.
    """
    return datenquelle_speichern(
        name=name,
        typ=typ,
        status="demo_verbunden",
        auth_typ=auth_typ,
        demo_modus=True,
        letzte_meldung=(
            "Lokale Testverbindung eingerichtet."
        ),
    )
