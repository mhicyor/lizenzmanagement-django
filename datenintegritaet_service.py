import re

from database import verbindung_oeffnen


QUELLENMUSTER = re.compile(r"^(?:rest_api|csv|ad):(\d+)$")


def _fremdschluesselfehler_laden(verbindung):
    return [
        {
            "tabelle": zeile[0],
            "zeile": zeile[1],
            "referenz": zeile[2],
            "schluessel": zeile[3],
        }
        for zeile in verbindung.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
    ]


def _verwaiste_verweise_bereinigen(verbindung):
    geloescht = {}

    for tabelle in (
        "synchronisationslaeufe",
        "synchronisation_status",
        "gruppen_mapping",
    ):
        cursor = verbindung.execute(
            f"""
            DELETE FROM {tabelle}
            WHERE datenquelle_id NOT IN (
                SELECT id FROM datenquellen
            )
            """
        )
        geloescht[tabelle] = max(0, int(cursor.rowcount or 0))

    cursor = verbindung.execute(
        """
        DELETE FROM lizenz_erkennungsregeln
        WHERE datenquelle_id IS NOT NULL
          AND datenquelle_id NOT IN (
              SELECT id FROM datenquellen
          )
        """
    )
    geloescht["lizenz_erkennungsregeln"] = max(
        0,
        int(cursor.rowcount or 0),
    )

    cursor = verbindung.execute(
        """
        UPDATE gruppen_mapping
        SET lizenz_id = NULL,
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE lizenz_id IS NOT NULL
          AND lizenz_id NOT IN (
              SELECT id FROM lizenzen
          )
        """
    )
    geloescht["gruppen_mapping_lizenzverweise"] = max(
        0,
        int(cursor.rowcount or 0),
    )

    return geloescht


def _quellenkandidaten_laden(verbindung):
    kandidaten = {}

    for lizenz_id, datenquelle_id in verbindung.execute(
        """
        SELECT DISTINCT regel.lizenz_id, regel.datenquelle_id
        FROM lizenz_erkennungsregeln AS regel
        JOIN datenquellen AS quelle
          ON quelle.id = regel.datenquelle_id
        WHERE regel.aktiv = 1
          AND quelle.aktiv = 1
        """
    ).fetchall():
        kandidaten.setdefault(int(lizenz_id), set()).add(
            int(datenquelle_id)
        )

    for lizenz_id, quelle in verbindung.execute(
        """
        SELECT DISTINCT lizenz_id, quelle
        FROM lizenz_zuweisungen
        WHERE status = 'aktiv'
          AND TRIM(COALESCE(quelle, '')) != ''
        """
    ).fetchall():
        treffer = QUELLENMUSTER.match(str(quelle or "").strip())

        if not treffer:
            continue

        datenquelle_id = int(treffer.group(1))
        vorhanden = verbindung.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE id = ? AND aktiv = 1
            """,
            (datenquelle_id,),
        ).fetchone()

        if vorhanden is not None:
            kandidaten.setdefault(int(lizenz_id), set()).add(
                datenquelle_id
            )

    return kandidaten


def _lizenz_eigentum_reparieren(verbindung):
    kandidaten = _quellenkandidaten_laden(verbindung)
    verknuepft = 0
    normalisiert = 0
    zurueckgesetzt = 0
    mehrdeutig = 0

    lizenzen = verbindung.execute(
        """
        SELECT id, COALESCE(datenquelle, 'manuell'), datenquelle_id
        FROM lizenzen
        """
    ).fetchall()

    for lizenz_id, datenquelle, datenquelle_id in lizenzen:
        lizenz_id = int(lizenz_id)
        aktuelle_quelle = None

        if datenquelle_id is not None:
            aktuelle_quelle = verbindung.execute(
                """
                SELECT id, typ
                FROM datenquellen
                WHERE id = ? AND aktiv = 1
                """,
                (datenquelle_id,),
            ).fetchone()

        if aktuelle_quelle is not None:
            if str(datenquelle or "").strip() != str(aktuelle_quelle[1]):
                verbindung.execute(
                    """
                    UPDATE lizenzen
                    SET datenquelle = ?, api_sync_aktiv = 1
                    WHERE id = ?
                    """,
                    (aktuelle_quelle[1], lizenz_id),
                )
                normalisiert += 1
            continue

        lizenz_kandidaten = kandidaten.get(lizenz_id, set())

        if len(lizenz_kandidaten) == 1:
            neue_id = next(iter(lizenz_kandidaten))
            neue_quelle = verbindung.execute(
                "SELECT typ FROM datenquellen WHERE id = ?",
                (neue_id,),
            ).fetchone()
            verbindung.execute(
                """
                UPDATE lizenzen
                SET datenquelle = ?,
                    datenquelle_id = ?,
                    api_sync_aktiv = 1
                WHERE id = ?
                """,
                (neue_quelle[0], neue_id, lizenz_id),
            )
            verknuepft += 1
        elif len(lizenz_kandidaten) > 1:
            mehrdeutig += 1
        elif datenquelle_id is not None:
            verbindung.execute(
                """
                UPDATE lizenzen
                SET datenquelle = 'manuell',
                    datenquelle_id = NULL,
                    api_sync_aktiv = 0
                WHERE id = ?
                """,
                (lizenz_id,),
            )
            zurueckgesetzt += 1

    return {
        "verknuepft": verknuepft,
        "normalisiert": normalisiert,
        "zurueckgesetzt": zurueckgesetzt,
        "mehrdeutig": mehrdeutig,
    }


def datenintegritaet_pruefen(reparieren=False):
    verbindung = verbindung_oeffnen()

    try:
        vorher = _fremdschluesselfehler_laden(verbindung)
        geloescht = {}
        lizenz_eigentum = {
            "verknuepft": 0,
            "normalisiert": 0,
            "zurueckgesetzt": 0,
            "mehrdeutig": 0,
        }

        if reparieren:
            verbindung.execute("BEGIN IMMEDIATE")
            geloescht = _verwaiste_verweise_bereinigen(verbindung)
            lizenz_eigentum = _lizenz_eigentum_reparieren(verbindung)
            verbindung.commit()

        nachher = _fremdschluesselfehler_laden(verbindung)

        return {
            "repariert": bool(reparieren),
            "fremdschluesselfehler_vorher": len(vorher),
            "fremdschluesselfehler_nachher": len(nachher),
            "verwaiste_verweise": vorher,
            "geloescht": geloescht,
            "lizenz_eigentum": lizenz_eigentum,
        }

    except Exception:
        verbindung.rollback()
        raise

    finally:
        verbindung.close()
