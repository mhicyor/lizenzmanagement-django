from database import verbindung_oeffnen


def lade_anbieter(nur_aktive=True):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    if nur_aktive:
        cursor.execute("""
            SELECT
                id,
                name,
                beschreibung,
                webseite,
                aktiv,
                erstellt_am,
                aktualisiert_am
            FROM anbieter
            WHERE aktiv = 1
            ORDER BY name
        """)
    else:
        cursor.execute("""
            SELECT
                id,
                name,
                beschreibung,
                webseite,
                aktiv,
                erstellt_am,
                aktualisiert_am
            FROM anbieter
            ORDER BY aktiv DESC, name
        """)

    daten = cursor.fetchall()
    verbindung.close()

    return daten


def lade_anbieter_details(anbieter_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            beschreibung,
            webseite,
            aktiv,
            erstellt_am,
            aktualisiert_am
        FROM anbieter
        WHERE id = ?
    """, (anbieter_id,))

    anbieter = cursor.fetchone()
    verbindung.close()

    return anbieter


def anzahl_lizenzen_mit_anbieter(anbieter_name):
    anbieter_name = (anbieter_name or "").strip()

    if not anbieter_name:
        return 0

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM lizenzen
        WHERE LOWER(TRIM(anbieter)) = LOWER(TRIM(?))
    """, (anbieter_name,))

    anzahl = cursor.fetchone()[0] or 0

    verbindung.close()

    return anzahl


def anbieter_hinzufuegen(name, beschreibung="", webseite=""):
    name = (name or "").strip()
    beschreibung = (beschreibung or "").strip()
    webseite = (webseite or "").strip()

    if not name:
        return False, "Bitte einen Anbieternamen eingeben.", None

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT id
        FROM anbieter
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
    """, (name,))

    vorhandener_anbieter = cursor.fetchone()

    if vorhandener_anbieter:
        verbindung.close()
        return False, "Dieser Anbieter existiert bereits.", vorhandener_anbieter[0]

    cursor.execute("""
        INSERT INTO anbieter (
            name,
            beschreibung,
            webseite,
            aktiv,
            erstellt_am,
            aktualisiert_am
        )
        VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        name,
        beschreibung,
        webseite,
    ))

    neue_id = cursor.lastrowid

    verbindung.commit()
    verbindung.close()

    return True, "Anbieter wurde hinzugefügt.", neue_id


def anbieter_aktualisieren(anbieter_id, name, beschreibung="", webseite="", aktiv="1"):
    name = (name or "").strip()
    beschreibung = (beschreibung or "").strip()
    webseite = (webseite or "").strip()

    try:
        aktiv = int(aktiv)
    except (TypeError, ValueError):
        aktiv = 1

    if aktiv not in [0, 1]:
        aktiv = 1

    if not name:
        return False, "Bitte einen Anbieternamen eingeben."

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT id
        FROM anbieter
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
          AND id != ?
    """, (name, anbieter_id))

    vorhandener_anbieter = cursor.fetchone()

    if vorhandener_anbieter:
        verbindung.close()
        return False, "Ein anderer Anbieter mit diesem Namen existiert bereits."

    cursor.execute("""
        UPDATE anbieter
        SET
            name = ?,
            beschreibung = ?,
            webseite = ?,
            aktiv = ?,
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        name,
        beschreibung,
        webseite,
        aktiv,
        anbieter_id,
    ))

    verbindung.commit()
    verbindung.close()

    return True, "Anbieter wurde aktualisiert."


def anbieter_deaktivieren(anbieter_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        UPDATE anbieter
        SET
            aktiv = 0,
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (anbieter_id,))

    verbindung.commit()
    verbindung.close()


def anbieter_reaktivieren(anbieter_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        UPDATE anbieter
        SET
            aktiv = 1,
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (anbieter_id,))

    verbindung.commit()
    verbindung.close()


def anbieter_loeschen(anbieter_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            aktiv
        FROM anbieter
        WHERE id = ?
    """, (anbieter_id,))

    anbieter = cursor.fetchone()

    if anbieter is None:
        verbindung.close()
        return False, "Der Anbieter existiert nicht."

    anbieter_name = anbieter[1]
    aktiv = bool(anbieter[2])

    if aktiv:
        verbindung.close()
        return False, "Aktive Anbieter können nicht gelöscht werden. Bitte zuerst deaktivieren."

    cursor.execute("""
        SELECT COUNT(*)
        FROM lizenzen
        WHERE LOWER(TRIM(anbieter)) = LOWER(TRIM(?))
    """, (anbieter_name,))

    anzahl_lizenzen = cursor.fetchone()[0] or 0

    if anzahl_lizenzen > 0:
        verbindung.close()
        return False, "Der Anbieter kann nicht gelöscht werden, weil noch Lizenzen damit verknüpft sind."

    cursor.execute("""
        DELETE FROM anbieter
        WHERE id = ?
    """, (anbieter_id,))

    verbindung.commit()
    verbindung.close()

    return True, "Der Anbieter wurde endgültig gelöscht."