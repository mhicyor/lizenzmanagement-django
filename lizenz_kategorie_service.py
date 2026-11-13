import re
from database import verbindung_oeffnen


def slug_erzeugen(name):
    slug = name.strip().lower()
    slug = slug.replace("ä", "ae")
    slug = slug.replace("ö", "oe")
    slug = slug.replace("ü", "ue")
    slug = slug.replace("ß", "ss")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")

    if not slug:
        slug = "kategorie"

    return slug


def slug_eindeutig_machen(cursor, slug, kategorie_id=None):
    basis_slug = slug
    zaehler = 2

    while True:
        if kategorie_id:
            cursor.execute(
                """
                SELECT id
                FROM lizenz_kategorien
                WHERE slug = ?
                AND id != ?
                """,
                (slug, kategorie_id)
            )
        else:
            cursor.execute(
                """
                SELECT id
                FROM lizenz_kategorien
                WHERE slug = ?
                """,
                (slug,)
            )

        treffer = cursor.fetchone()

        if treffer is None:
            return slug

        slug = f"{basis_slug}_{zaehler}"
        zaehler += 1


def lade_lizenz_kategorien(nur_aktive=True, inklusive_archiviert=False):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    sql = """
        SELECT
            id,
            name,
            beschreibung,
            lizenzlogik,
            typische_zuordnung,
            interne_lizenzklasse,
            aktiv,
            slug,
            standard_zuweisungsart,
            archiviert,
            archiviert_am,
            archivierungsgrund,
            sortierung,
            erstellt_am,
            aktualisiert_am
        FROM lizenz_kategorien
    """

    bedingungen = []
    parameter = []

    if nur_aktive:
        bedingungen.append("aktiv = 1")

    if not inklusive_archiviert:
        bedingungen.append("archiviert = 0")

    if bedingungen:
        sql += " WHERE " + " AND ".join(bedingungen)

    sql += " ORDER BY sortierung ASC, name ASC"

    cursor.execute(sql, parameter)
    kategorien = cursor.fetchall()

    verbindung.close()
    return kategorien


def lade_lizenz_kategorie_details(kategorie_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute(
        """
        SELECT
            id,
            name,
            beschreibung,
            lizenzlogik,
            typische_zuordnung,
            interne_lizenzklasse,
            aktiv,
            slug,
            standard_zuweisungsart,
            archiviert,
            archiviert_am,
            archivierungsgrund,
            sortierung,
            erstellt_am,
            aktualisiert_am
        FROM lizenz_kategorien
        WHERE id = ?
        """,
        (kategorie_id,)
    )

    kategorie = cursor.fetchone()
    verbindung.close()

    return kategorie


def lizenz_kategorie_wird_verwendet(kategorie_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM lizenzen
        WHERE kategorie_id = ?
        """,
        (kategorie_id,)
    )

    anzahl = cursor.fetchone()[0]

    verbindung.close()
    return anzahl > 0


def anzahl_lizenzen_mit_kategorie(kategorie_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM lizenzen
        WHERE kategorie_id = ?
        """,
        (kategorie_id,)
    )

    anzahl = cursor.fetchone()[0]

    verbindung.close()
    return anzahl


def lizenz_kategorie_hinzufuegen(
    name,
    beschreibung,
    lizenzlogik,
    typische_zuordnung,
    interne_lizenzklasse,
    standard_zuweisungsart,
    sortierung=100
):
    name = name.strip()
    beschreibung = beschreibung.strip()
    lizenzlogik = lizenzlogik.strip()
    typische_zuordnung = typische_zuordnung.strip()
    interne_lizenzklasse = interne_lizenzklasse.strip()
    standard_zuweisungsart = standard_zuweisungsart.strip()

    if not name:
        return False, "Bitte einen Kategorienamen eintragen.", None

    if interne_lizenzklasse not in ["benutzer", "geraet", "server"]:
        return False, "Bitte eine gültige interne Lizenzklasse wählen.", None

    if standard_zuweisungsart not in ["benutzer", "geraet", "server"]:
        return False, "Bitte eine gültige Standard-Zuweisungsart wählen.", None

    try:
        sortierung = int(sortierung)
    except (TypeError, ValueError):
        sortierung = 100

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    slug = slug_erzeugen(name)
    slug = slug_eindeutig_machen(cursor, slug)

    cursor.execute(
        """
        SELECT id
        FROM lizenz_kategorien
        WHERE LOWER(name) = LOWER(?)
        """,
        (name,)
    )

    vorhandene_kategorie = cursor.fetchone()

    if vorhandene_kategorie:
        verbindung.close()
        return False, "Eine Kategorie mit diesem Namen existiert bereits.", None

    cursor.execute(
        """
        INSERT INTO lizenz_kategorien (
            name,
            slug,
            beschreibung,
            lizenzlogik,
            typische_zuordnung,
            interne_lizenzklasse,
            standard_zuweisungsart,
            aktiv,
            archiviert,
            sortierung,
            erstellt_am,
            aktualisiert_am
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            name,
            slug,
            beschreibung,
            lizenzlogik,
            typische_zuordnung,
            interne_lizenzklasse,
            standard_zuweisungsart,
            sortierung,
        )
    )

    neue_id = cursor.lastrowid

    verbindung.commit()
    verbindung.close()

    return True, "Kategorie wurde hinzugefügt.", neue_id


def lizenz_kategorie_aktualisieren(
    kategorie_id,
    name,
    beschreibung,
    lizenzlogik,
    typische_zuordnung,
    interne_lizenzklasse,
    standard_zuweisungsart,
    aktiv,
    sortierung=100
):
    name = name.strip()
    beschreibung = beschreibung.strip()
    lizenzlogik = lizenzlogik.strip()
    typische_zuordnung = typische_zuordnung.strip()
    interne_lizenzklasse = interne_lizenzklasse.strip()
    standard_zuweisungsart = standard_zuweisungsart.strip()

    if not name:
        return False, "Bitte einen Kategorienamen eintragen."

    if interne_lizenzklasse not in ["benutzer", "geraet", "server"]:
        return False, "Bitte eine gültige interne Lizenzklasse wählen."

    if standard_zuweisungsart not in ["benutzer", "geraet", "server"]:
        return False, "Bitte eine gültige Standard-Zuweisungsart wählen."

    try:
        sortierung = int(sortierung)
    except (TypeError, ValueError):
        sortierung = 100

    aktiv_wert = 1 if str(aktiv) == "1" else 0

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute(
        """
        SELECT id
        FROM lizenz_kategorien
        WHERE id = ?
        """,
        (kategorie_id,)
    )

    vorhandene_kategorie = cursor.fetchone()

    if vorhandene_kategorie is None:
        verbindung.close()
        return False, "Die ausgewählte Kategorie existiert nicht."

    cursor.execute(
        """
        SELECT id
        FROM lizenz_kategorien
        WHERE LOWER(name) = LOWER(?)
        AND id != ?
        """,
        (name, kategorie_id)
    )

    name_belegt = cursor.fetchone()

    if name_belegt:
        verbindung.close()
        return False, "Eine andere Kategorie mit diesem Namen existiert bereits."

    slug = slug_erzeugen(name)
    slug = slug_eindeutig_machen(cursor, slug, kategorie_id)

    cursor.execute(
        """
        UPDATE lizenz_kategorien
        SET
            name = ?,
            slug = ?,
            beschreibung = ?,
            lizenzlogik = ?,
            typische_zuordnung = ?,
            interne_lizenzklasse = ?,
            standard_zuweisungsart = ?,
            aktiv = ?,
            sortierung = ?,
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            name,
            slug,
            beschreibung,
            lizenzlogik,
            typische_zuordnung,
            interne_lizenzklasse,
            standard_zuweisungsart,
            aktiv_wert,
            sortierung,
            kategorie_id,
        )
    )

    verbindung.commit()
    verbindung.close()

    return True, "Kategorie wurde aktualisiert."


def lizenz_kategorie_archivieren(kategorie_id, archivierungsgrund=""):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute(
        """
        SELECT id
        FROM lizenz_kategorien
        WHERE id = ?
        """,
        (kategorie_id,)
    )

    kategorie = cursor.fetchone()

    if kategorie is None:
        verbindung.close()
        return False, "Die ausgewählte Kategorie existiert nicht."

    cursor.execute(
        """
        UPDATE lizenz_kategorien
        SET
            aktiv = 0,
            archiviert = 1,
            archiviert_am = CURRENT_TIMESTAMP,
            archivierungsgrund = ?,
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            archivierungsgrund.strip(),
            kategorie_id,
        )
    )

    verbindung.commit()
    verbindung.close()

    return True, "Kategorie wurde archiviert."


def lizenz_kategorie_reaktivieren(kategorie_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute(
        """
        SELECT id
        FROM lizenz_kategorien
        WHERE id = ?
        """,
        (kategorie_id,)
    )

    kategorie = cursor.fetchone()

    if kategorie is None:
        verbindung.close()
        return False, "Die ausgewählte Kategorie existiert nicht."

    cursor.execute(
        """
        UPDATE lizenz_kategorien
        SET
            aktiv = 1,
            archiviert = 0,
            archiviert_am = NULL,
            archivierungsgrund = '',
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (kategorie_id,)
    )

    verbindung.commit()
    verbindung.close()

    return True, "Kategorie wurde reaktiviert."


def interne_lizenzlogik_fuer_kategorie(kategorie_id):
    kategorie = lade_lizenz_kategorie_details(kategorie_id)

    if kategorie is None:
        return "benutzer", "benutzer"

    interne_lizenzklasse = kategorie[5] or "benutzer"
    standard_zuweisungsart = kategorie[8] or interne_lizenzklasse

    return interne_lizenzklasse, standard_zuweisungsart


def lade_lizenz_kategorie(kategorie_id):
    return lade_lizenz_kategorie_details(kategorie_id)


def lizenz_kategorie_deaktivieren(kategorie_id, archivierungsgrund=""):
    return lizenz_kategorie_archivieren(kategorie_id, archivierungsgrund)

def lizenz_kategorie_loeschen(kategorie_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            archiviert
        FROM lizenz_kategorien
        WHERE id = ?
    """, (kategorie_id,))

    kategorie = cursor.fetchone()

    if kategorie is None:
        verbindung.close()
        return False, "Die Kategorie existiert nicht."

    if not bool(kategorie[2]):
        verbindung.close()
        return False, "Aktive Kategorien können nicht gelöscht werden. Bitte zuerst archivieren."

    cursor.execute("""
        SELECT COUNT(*)
        FROM lizenzen
        WHERE kategorie_id = ?
    """, (kategorie_id,))

    anzahl_lizenzen = cursor.fetchone()[0] or 0

    if anzahl_lizenzen > 0:
        verbindung.close()
        return False, "Die Kategorie kann nicht gelöscht werden, weil noch Lizenzen damit verknüpft sind."

    cursor.execute("""
        DELETE FROM lizenz_kategorien
        WHERE id = ?
    """, (kategorie_id,))

    verbindung.commit()
    verbindung.close()

    return True, "Die archivierte Kategorie wurde endgültig gelöscht."