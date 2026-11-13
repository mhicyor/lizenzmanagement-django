import sqlite3
from typing import Any

from datenquelle_service import DATENBANK_DATEI
from sqlite_context import sqlite_verbindung


def lizenz_erkennungsregeln_laden(
    datenquelle_id: int | None = None,
) -> list[dict[str, Any]]:
    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row

        if datenquelle_id is None:
            zeilen = verbindung.execute(
                """
                SELECT
                    r.id,
                    r.datenquelle_id,
                    r.muster,
                    r.lizenz_id,
                    l.name AS lizenzname,
                    r.aktiv,
                    r.bemerkung
                FROM lizenz_erkennungsregeln r
                JOIN lizenzen l
                    ON l.id = r.lizenz_id
                WHERE r.aktiv = 1
                ORDER BY r.muster
                """
            ).fetchall()
        else:
            zeilen = verbindung.execute(
                """
                SELECT
                    r.id,
                    r.datenquelle_id,
                    r.muster,
                    r.lizenz_id,
                    l.name AS lizenzname,
                    r.aktiv,
                    r.bemerkung
                FROM lizenz_erkennungsregeln r
                JOIN lizenzen l
                    ON l.id = r.lizenz_id
                WHERE r.aktiv = 1
                  AND (
                    r.datenquelle_id = ?
                    OR r.datenquelle_id IS NULL
                  )
                ORDER BY r.muster
                """,
                (datenquelle_id,),
            ).fetchall()

    return [dict(zeile) for zeile in zeilen]


def lizenz_aus_gruppen_erkennen(
    gruppen: list[str],
    regeln: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    treffer = []

    for gruppe in gruppen:
        gruppen_text = str(gruppe or "").lower()

        for regel in regeln:
            muster = str(
                regel.get("muster", "")
            ).strip().lower()

            if not muster:
                continue

            if muster in gruppen_text:
                treffer.append(
                    {
                        "gruppe": gruppe,
                        "muster": regel["muster"],
                        "lizenz_id": regel["lizenz_id"],
                        "lizenzname": regel["lizenzname"],
                    }
                )

    return treffer


def lizenz_erkennungsregel_speichern(
    datenquelle_id: int | None,
    muster: str,
    lizenz_id: int,
    bemerkung: str = "",
) -> int:
    muster = str(muster or "").strip()

    if not muster:
        raise ValueError("Das Muster darf nicht leer sein.")

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        cursor = verbindung.execute(
            """
            INSERT OR IGNORE INTO lizenz_erkennungsregeln (
                datenquelle_id,
                muster,
                lizenz_id,
                bemerkung
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                datenquelle_id,
                muster,
                lizenz_id,
                bemerkung,
            ),
        )

        verbindung.commit()

        if cursor.lastrowid:
            return int(cursor.lastrowid)

        zeile = verbindung.execute(
            """
            SELECT id
            FROM lizenz_erkennungsregeln
            WHERE (
                datenquelle_id = ?
                OR (
                    datenquelle_id IS NULL
                    AND ? IS NULL
                )
            )
              AND muster = ?
              AND lizenz_id = ?
            LIMIT 1
            """,
            (
                datenquelle_id,
                datenquelle_id,
                muster,
                lizenz_id,
            ),
        ).fetchone()

    return int(zeile[0]) if zeile else 0
