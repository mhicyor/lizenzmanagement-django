from database import verbindung_oeffnen


def lade_zuweisungsziel_typen(nur_aktive=True):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    if nur_aktive:
        cursor.execute("""
            SELECT
                id,
                name,
                slug,
                beschreibung,
                basistyp,
                aktiv,
                sortierung
            FROM zuweisungsziel_typen
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
                basistyp,
                aktiv,
                sortierung
            FROM zuweisungsziel_typen
            ORDER BY aktiv DESC, sortierung ASC, name ASC
        """)

    zieltypen = cursor.fetchall()
    verbindung.close()

    return zieltypen


def lade_zuweisungsziel_typ(zieltyp_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            slug,
            beschreibung,
            basistyp,
            aktiv,
            sortierung
        FROM zuweisungsziel_typen
        WHERE id = ?
    """, (zieltyp_id,))

    zieltyp = cursor.fetchone()
    verbindung.close()

    return zieltyp


def standard_zuweisungszieltyp_id_laden(basistyp="benutzer"):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT id
        FROM zuweisungsziel_typen
        WHERE basistyp = ?
          AND aktiv = 1
        ORDER BY sortierung ASC, id ASC
        LIMIT 1
    """, (basistyp,))

    zieltyp = cursor.fetchone()
    verbindung.close()

    if zieltyp:
        return zieltyp[0]

    return None
