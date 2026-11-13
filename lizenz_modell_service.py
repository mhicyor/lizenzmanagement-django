from database import verbindung_oeffnen


def lade_lizenz_modelle(nur_aktive=True):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    if nur_aktive:
        cursor.execute("""
            SELECT
                id,
                name,
                slug,
                beschreibung,
                logik_typ,
                aktiv,
                sortierung
            FROM lizenz_modelle
            WHERE aktiv = 1
            ORDER BY sortierung ASC, name ASC
        """)
    else:
        cursor.execute("""
            SELECT
                id,
                name,
                slug,
                beschreibung,
                logik_typ,
                aktiv,
                sortierung
            FROM lizenz_modelle
            ORDER BY aktiv DESC, sortierung ASC, name ASC
        """)

    modelle = cursor.fetchall()
    verbindung.close()

    return modelle


def lade_lizenz_modell(modell_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            slug,
            beschreibung,
            logik_typ,
            aktiv,
            sortierung
        FROM lizenz_modelle
        WHERE id = ?
    """, (modell_id,))

    modell = cursor.fetchone()
    verbindung.close()

    return modell


def standard_lizenzmodell_id_laden(logik_typ="nutzerbasiert"):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT id
        FROM lizenz_modelle
        WHERE logik_typ = ?
          AND aktiv = 1
        ORDER BY sortierung ASC, id ASC
        LIMIT 1
    """, (logik_typ,))

    modell = cursor.fetchone()
    verbindung.close()

    if modell:
        return modell[0]

    return None
