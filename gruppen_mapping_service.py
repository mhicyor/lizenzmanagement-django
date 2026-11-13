import sqlite3
from typing import Any

from datenquelle_service import DATENBANK_DATEI
from sqlite_context import sqlite_verbindung


ERLAUBTE_KLASSIFIKATIONEN = {
    "produktprofil",
    "mapping_kandidat",
    "organisation",
    "technisch",
    "ignorieren",
}


def gruppen_mapping_vorschlaege_speichern(
    datenquelle_id: int,
    gruppen: list[dict[str, Any]],
) -> int:
    angelegt = 0

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        for gruppe in gruppen:
            gruppenname = str(gruppe.get("name", "")).strip()
            klassifikation = str(
                gruppe.get("klassifikation", "mapping_kandidat")
            ).strip()

            if not gruppenname:
                continue

            if klassifikation not in ERLAUBTE_KLASSIFIKATIONEN:
                klassifikation = "mapping_kandidat"

            cursor = verbindung.execute(
                """
                INSERT OR IGNORE INTO gruppen_mapping (
                    datenquelle_id,
                    gruppenname,
                    klassifikation
                )
                VALUES (?, ?, ?)
                """,
                (
                    datenquelle_id,
                    gruppenname,
                    klassifikation,
                ),
            )

            angelegt += cursor.rowcount

        verbindung.commit()

    return angelegt


def gruppen_mapping_laden(
    datenquelle_id: int,
) -> list[dict[str, Any]]:
    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeilen = verbindung.execute(
            """
            SELECT
                gm.id,
                gm.datenquelle_id,
                gm.gruppenname,
                gm.klassifikation,
                gm.lizenz_id,
                l.name AS lizenzname,
                gm.bemerkung,
                gm.aktiv
            FROM gruppen_mapping gm
            LEFT JOIN lizenzen l
                ON l.id = gm.lizenz_id
            WHERE gm.datenquelle_id = ?
            ORDER BY
                gm.klassifikation,
                gm.gruppenname
            """,
            (datenquelle_id,),
        ).fetchall()

    return [dict(zeile) for zeile in zeilen]


def gruppen_mapping_aktualisieren(
    mapping_id: int,
    klassifikation: str,
    lizenz_id: int | None = None,
    bemerkung: str = "",
) -> bool:
    if klassifikation not in ERLAUBTE_KLASSIFIKATIONEN:
        raise ValueError("Ungültige Klassifikation.")

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        cursor = verbindung.execute(
            """
            UPDATE gruppen_mapping
            SET
                klassifikation = ?,
                lizenz_id = ?,
                bemerkung = ?,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (klassifikation, lizenz_id, bemerkung, mapping_id),
        )

        verbindung.commit()

    return cursor.rowcount > 0


def gruppen_mapping_entscheidung_speichern(
    datenquelle_id: int,
    gruppenname: str,
    klassifikation: str,
    lizenz_id: int | None = None,
    bemerkung: str = "",
) -> int:
    gruppenname = str(gruppenname or "").strip()

    if not gruppenname:
        raise ValueError("Der Gruppenname darf nicht leer sein.")

    if klassifikation not in ERLAUBTE_KLASSIFIKATIONEN:
        raise ValueError("Ungültige Klassifikation.")

    if klassifikation != "produktprofil":
        lizenz_id = None

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.execute(
            """
            INSERT INTO gruppen_mapping (
                datenquelle_id,
                gruppenname,
                klassifikation,
                lizenz_id,
                bemerkung,
                aktiv
            )
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(datenquelle_id, gruppenname)
            DO UPDATE SET
                klassifikation = excluded.klassifikation,
                lizenz_id = excluded.lizenz_id,
                bemerkung = excluded.bemerkung,
                aktiv = 1,
                aktualisiert_am = CURRENT_TIMESTAMP
            """,
            (
                datenquelle_id,
                gruppenname,
                klassifikation,
                lizenz_id,
                bemerkung,
            ),
        )

        zeile = verbindung.execute(
            """
            SELECT id
            FROM gruppen_mapping
            WHERE datenquelle_id = ?
              AND gruppenname = ?
            LIMIT 1
            """,
            (datenquelle_id, gruppenname),
        ).fetchone()

        verbindung.commit()

    return int(zeile[0])


def aktive_lizenz_mappings_laden(
    datenquelle_id: int,
) -> dict[str, dict[str, Any]]:
    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeilen = verbindung.execute(
            """
            SELECT
                gruppenname,
                lizenz_id,
                klassifikation
            FROM gruppen_mapping
            WHERE datenquelle_id = ?
              AND aktiv = 1
              AND lizenz_id IS NOT NULL
            """,
            (datenquelle_id,),
        ).fetchall()

    return {
        zeile["gruppenname"]: dict(zeile)
        for zeile in zeilen
    }
