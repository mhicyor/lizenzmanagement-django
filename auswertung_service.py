from datetime import date, datetime

from database import verbindung_oeffnen
from kosten_service import berechne_monatskosten
from benutzer_service import ist_technisches_benutzerkonto
from benutzer_status_service import deaktivierungsgrund_anzeige


def _ist_deaktivierter_benutzer_relevante_person(
    name,
    email,
    benutzername="",
):
    name_text = str(name or "").strip()
    email_text = str(email or "").strip()

    if not name_text or not email_text:
        return False

    return not ist_technisches_benutzerkonto(
        name_text,
        benutzername,
        email_text,
    )


def lade_dashboard_statistik():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("SELECT COUNT(*) FROM lizenzen")
    anzahl_lizenztypen = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(COALESCE(anzahl, 0)), 0)
        FROM lizenzen
    """)
    gesamt_lizenzen = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(
            COALESCE(
                l.externer_verbrauch,
                COALESCE(b.anzahl, 0) + COALESCE(g.anzahl, 0)
            )
        ), 0)
        FROM lizenzen l
        LEFT JOIN (
            SELECT lizenz_id, COUNT(*) AS anzahl
            FROM zuweisungen
            WHERE status = 'aktiv'
            GROUP BY lizenz_id
        ) b ON b.lizenz_id = l.id
        LEFT JOIN (
            SELECT lizenz_id, COUNT(*) AS anzahl
            FROM lizenz_zuweisungen
            WHERE status = 'aktiv' AND ziel_typ != 'benutzer'
            GROUP BY lizenz_id
        ) g ON g.lizenz_id = l.id
    """)
    vergebene_lizenzen = cursor.fetchone()[0]

    cursor.execute("""
        SELECT name, benutzername, email
        FROM benutzer
        WHERE aktiv = 1
    """)
    aktive_benutzer = sum(
        1
        for name, benutzername, email in cursor.fetchall()
        if not ist_technisches_benutzerkonto(
            name,
            benutzername,
            email,
        )
    )

    cursor.execute("""
        SELECT
            l.kosten,
            l.kostenmodell,
            COALESCE(l.anzahl, 0) AS menge
        FROM lizenzen l
    """)

    kosten_daten = cursor.fetchall()
    verbindung.close()

    gesamtkosten = 0

    for kosten, kostenmodell, menge in kosten_daten:
        gesamtkosten += berechne_monatskosten(
            kosten,
            kostenmodell,
            menge
        )

    freie_lizenzen = max(0, gesamt_lizenzen - vergebene_lizenzen)

    return {
        "anzahl_lizenztypen": anzahl_lizenztypen,
        "gesamt_lizenzen": gesamt_lizenzen,
        "vergebene_lizenzen": vergebene_lizenzen,
        "freie_lizenzen": freie_lizenzen,
        "aktive_benutzer": aktive_benutzer,
        "gesamtkosten": gesamtkosten
    }

def lade_lizenzkategorien_statistik():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            COALESCE(k.name, 'Ohne Kategorie') AS kategorie_name,
            COALESCE(k.slug, 'ohne_kategorie') AS kategorie_slug,
            COUNT(l.id) AS anzahl_lizenztypen,
            COALESCE(SUM(l.anzahl), 0) AS anzahl_gesamt,
            COALESCE(SUM(
                COALESCE(
                    l.externer_verbrauch,
                    COALESCE(za.anzahl, 0) + COALESCE(zg.anzahl, 0)
                )
            ), 0) AS anzahl_vergeben,
            COALESCE(SUM(
                CASE
                    WHEN l.kostenmodell = 'fortlaufend'
                        THEN COALESCE(l.kosten, 0) * COALESCE(l.anzahl, 0)
                    WHEN l.kostenmodell = 'jaehrlich'
                        THEN COALESCE(l.kosten, 0) * COALESCE(l.anzahl, 0) / 12
                    ELSE 0
                END
            ), 0) AS monatskosten
        FROM lizenzen l
        LEFT JOIN lizenz_kategorien k
            ON l.kategorie_id = k.id
        LEFT JOIN (
            SELECT lizenz_id, COUNT(*) AS anzahl
            FROM zuweisungen
            WHERE status = 'aktiv'
            GROUP BY lizenz_id
        ) za ON za.lizenz_id = l.id
        LEFT JOIN (
            SELECT lizenz_id, COUNT(*) AS anzahl
            FROM lizenz_zuweisungen
            WHERE status = 'aktiv' AND ziel_typ != 'benutzer'
            GROUP BY lizenz_id
        ) zg ON zg.lizenz_id = l.id
        GROUP BY
            COALESCE(k.name, 'Ohne Kategorie'),
            COALESCE(k.slug, 'ohne_kategorie')
        ORDER BY anzahl_lizenztypen DESC, kategorie_name
    """)

    daten = cursor.fetchall()
    verbindung.close()

    statistik = []

    for eintrag in daten:
        kategorie_name = eintrag[0]
        kategorie_slug = eintrag[1]
        anzahl_lizenztypen = eintrag[2] or 0
        anzahl_gesamt = eintrag[3] or 0
        anzahl_vergeben = eintrag[4] or 0
        monatskosten = eintrag[5] or 0

        statistik.append({
            "kategorie_name": kategorie_name,
            "kategorie_slug": kategorie_slug,
            "anzahl_lizenzen": anzahl_lizenztypen,
            "anzahl_gesamt": anzahl_gesamt,
            "anzahl_vergeben": anzahl_vergeben,
            "theoretische_monatskosten": f"{float(monatskosten):.2f}",
        })

    return statistik

def lade_benutzer_lizenz_matrix(suchtext="", abteilung_filter=None):
    suchtext = suchtext.strip().lower()

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    if abteilung_filter and abteilung_filter != "Alle Abteilungen":
        cursor.execute("""
            SELECT
                benutzer.id,
                benutzer.externe_id,
                benutzer.name,
                benutzer.benutzername,
                benutzer.email,
                benutzer.abteilung,
                benutzer.aktiv,
                GROUP_CONCAT(lizenzen.name, ', ') AS lizenzliste,
                COUNT(lizenzen.id) AS anzahl_lizenzen,
                COALESCE(SUM(lizenzen.kosten), 0) AS kosten_summe
            FROM benutzer
            LEFT JOIN zuweisungen
                ON benutzer.id = zuweisungen.benutzer_id
                AND zuweisungen.status = 'aktiv'
            LEFT JOIN lizenzen
                ON zuweisungen.lizenz_id = lizenzen.id
            WHERE TRIM(benutzer.abteilung) = TRIM(?)
            GROUP BY benutzer.id
            ORDER BY benutzer.name
        """, (abteilung_filter,))
    else:
        cursor.execute("""
            SELECT
                benutzer.id,
                benutzer.externe_id,
                benutzer.name,
                benutzer.benutzername,
                benutzer.email,
                benutzer.abteilung,
                benutzer.aktiv,
                GROUP_CONCAT(lizenzen.name, ', ') AS lizenzliste,
                COUNT(lizenzen.id) AS anzahl_lizenzen,
                COALESCE(SUM(lizenzen.kosten), 0) AS kosten_summe
            FROM benutzer
            LEFT JOIN zuweisungen
                ON benutzer.id = zuweisungen.benutzer_id
                AND zuweisungen.status = 'aktiv'
            LEFT JOIN lizenzen
                ON zuweisungen.lizenz_id = lizenzen.id
            GROUP BY benutzer.id
            ORDER BY benutzer.name
        """)

    daten = cursor.fetchall()
    verbindung.close()

    gefilterte_daten = []

    for eintrag in daten:
        interne_id = eintrag[0]
        firmen_id_original = eintrag[1] or ""
        firmen_id = firmen_id_original

        if firmen_id.startswith("{") and firmen_id.endswith("}"):
            firmen_id = "—"

        name = eintrag[2] or ""
        benutzername = eintrag[3] or ""
        email = eintrag[4] or ""
        abteilung = eintrag[5] or ""
        aktiv = eintrag[6]
        lizenzliste = eintrag[7] or "Keine aktiven Lizenzen"
        anzahl_lizenzen = eintrag[8]
        kosten_summe = eintrag[9] or 0

        suchbasis = f"{interne_id} {firmen_id_original} {firmen_id} {name} {benutzername} {email} {abteilung} {lizenzliste}".lower()

        if suchtext and suchtext not in suchbasis:
            continue

        status = "aktiv" if aktiv == 1 else "deaktiviert"

        gefilterte_daten.append((
            interne_id,
            firmen_id,
            name,
            benutzername,
            email,
            abteilung,
            status,
            anzahl_lizenzen,
            lizenzliste,
            f"{kosten_summe:.2f} EUR"
        ))

    return gefilterte_daten


def lade_ablaufende_lizenzen(tage):
    heute = date.today()

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT name, anbieter, ablaufdatum, verlaengerungsdatum
        FROM lizenzen
        WHERE ablaufdatum IS NOT NULL AND ablaufdatum != ''
        ORDER BY ablaufdatum
    """)

    daten = cursor.fetchall()
    verbindung.close()

    gefundene_daten = []

    for eintrag in daten:
        try:
            ablaufdatum = datetime.strptime(eintrag[2], "%Y-%m-%d").date()
        except ValueError:
            continue

        resttage = (ablaufdatum - heute).days

        if resttage <= tage:
            gefundene_daten.append(
                (eintrag[0], eintrag[1], eintrag[2], resttage, eintrag[3])
            )

    return gefundene_daten


def lade_deaktivierte_benutzer_mit_lizenzen():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            benutzer.id,
            benutzer.name,
            benutzer.benutzername,
            benutzer.email,
            benutzer.abteilung,
            benutzer.quelle,
            benutzer.deaktivierungsgrund,
            lizenzen.id,
            lizenzen.name,
            lizenzen.kosten
        FROM zuweisungen
        JOIN benutzer ON zuweisungen.benutzer_id = benutzer.id
        JOIN lizenzen ON zuweisungen.lizenz_id = lizenzen.id
        WHERE benutzer.aktiv = 0
          AND zuweisungen.status = 'aktiv'
          AND TRIM(COALESCE(benutzer.email, '')) != ''
          AND COALESCE(
                NULLIF(TRIM(lizenzen.zuweisungsart), ''),
                NULLIF(TRIM(lizenzen.lizenzklasse), ''),
                'benutzer'
          ) = 'benutzer'
        ORDER BY benutzer.name, lizenzen.name
    """)

    daten = cursor.fetchall()
    formatierte_daten = []

    for eintrag in daten:
        benutzer_id = eintrag[0]
        benutzer_name = eintrag[1] or ""
        benutzername = eintrag[2] or ""
        email = eintrag[3] or ""
        abteilung = eintrag[4] or ""
        quelle = eintrag[5] or ""
        deaktivierungsgrund = eintrag[6] or ""
        lizenz_id = eintrag[7]
        lizenz_name = eintrag[8] or ""
        kosten = eintrag[9] or 0

        if not _ist_deaktivierter_benutzer_relevante_person(
            benutzer_name,
            email,
            benutzername,
        ):
            continue

        formatierte_daten.append({
            "benutzer_id": benutzer_id,
            "benutzer": benutzer_name,
            "benutzername": benutzername,
            "email": email,
            "abteilung": abteilung,
            "quelle": quelle,
            "deaktivierungsgrund": deaktivierungsgrund,
            "deaktivierungsgrund_anzeige": (
                deaktivierungsgrund_anzeige(
                    deaktivierungsgrund
                )
            ),
            "lizenz_id": lizenz_id,
            "lizenz": lizenz_name,
            "kosten": f"{kosten:.2f} EUR",
        })

    verbindung.close()

    return formatierte_daten
