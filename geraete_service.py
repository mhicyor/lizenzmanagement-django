from database import verbindung_oeffnen


def lade_geraete_uebersicht():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            inventarnummer,
            seriennummer,
            geraetetyp,
            status,
            CASE WHEN datenquelle_id IS NOT NULL
                OR COALESCE(quelle, 'manuell') NOT IN ('', 'manuell')
                THEN 'datenquelle' ELSE 'manuell' END,
            COALESCE(NULLIF(TRIM(erstellt_am), ''), zuletzt_synchronisiert),
            zuletzt_synchronisiert
        FROM geraete
        ORDER BY name
    """)

    daten = cursor.fetchall()
    verbindung.close()

    return daten


def geraet_hinzufuegen(name, inventarnummer, seriennummer, geraetetyp):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        INSERT INTO geraete
            (name, inventarnummer, seriennummer, geraetetyp, status, erstellt_am)
        VALUES (?, ?, ?, ?, ?, DATETIME('now'))
    """, (
        name,
        inventarnummer,
        seriennummer,
        geraetetyp,
        "aktiv"
    ))

    verbindung.commit()
    verbindung.close()


def lade_geraet_details(geraet_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            inventarnummer,
            seriennummer,
            geraetetyp,
            status
        FROM geraete
        WHERE id = ?
    """, (geraet_id,))

    geraet = cursor.fetchone()
    verbindung.close()

    return geraet

def geraet_aktualisieren(geraet_id, name, inventarnummer, seriennummer, geraetetyp, status):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        UPDATE geraete
        SET
            name = ?,
            inventarnummer = ?,
            seriennummer = ?,
            geraetetyp = ?,
            status = ?
        WHERE id = ?
    """, (
        name,
        inventarnummer,
        seriennummer,
        geraetetyp,
        status,
        geraet_id
    ))

    verbindung.commit()
    verbindung.close()


def geraet_loeschen(geraet_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        DELETE FROM lizenz_zuweisungen
        WHERE ziel_typ = 'geraet'
          AND ziel_id = ?
    """, (geraet_id,))

    cursor.execute("""
        DELETE FROM geraete
        WHERE id = ?
    """, (geraet_id,))

    verbindung.commit()
    verbindung.close()
