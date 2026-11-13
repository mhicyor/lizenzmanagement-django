from database import verbindung_oeffnen

from lizenz_model import (
    Lizenz,
    LizenzStammdaten,
    LizenzKlassifikation,
    LizenzKostenmodell,
    LizenzZuweisungsmodell,
    LizenzNutzungsmodell,
    LizenzVertragsdaten,
)


def lizenz_objekt_erstellen(datensatz, vergeben=0):
    stammdaten = LizenzStammdaten(
        id=datensatz["id"],
        name=datensatz["name"],
        anbieter=datensatz["anbieter"],
    )

    klassifikation = LizenzKlassifikation(
        lizenzklasse=datensatz.get("lizenzklasse"),
        technologiebereich=datensatz.get("technologiebereich"),
    )

    kostenmodell = LizenzKostenmodell(
        kosten=datensatz.get("kosten"),
        kostenmodell=datensatz.get("kostenmodell"),
    )

    zuweisungsmodell = LizenzZuweisungsmodell(
        zuweisungsart=datensatz.get("zuweisungsart"),
    )

    nutzungsmodell = LizenzNutzungsmodell(
        anzahl=datensatz.get("anzahl"),
        vergeben=vergeben,
    )

    vertragsdaten = LizenzVertragsdaten(
        ablaufdatum=datensatz.get("ablaufdatum"),
        verlaengerungsdatum=datensatz.get("verlaengerungsdatum"),
    )

    return Lizenz(
        stammdaten=stammdaten,
        klassifikation=klassifikation,
        kostenmodell=kostenmodell,
        zuweisungsmodell=zuweisungsmodell,
        nutzungsmodell=nutzungsmodell,
        vertragsdaten=vertragsdaten,
    )


def bereinige_text(wert, standard=""):
    if wert is None:
        return standard
    return str(wert).strip()


def bereinige_int(wert, standard=0):
    try:
        if wert is None or wert == "":
            return standard
        return int(wert)
    except (TypeError, ValueError):
        return standard


def bereinige_float(wert, standard=0.0):
    try:
        if wert is None or wert == "":
            return standard
        return float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        return standard


def bereinige_bool_int(wert):
    if wert in [True, 1, "1", "on", "true", "True", "ja", "Ja"]:
        return 1
    return 0


def _lizenz_zielart_aus_zeile(zuweisungsart, lizenzklasse):
    return (
        bereinige_text(zuweisungsart)
        or bereinige_text(lizenzklasse)
        or "benutzer"
    ).lower()


def _tabellenspalten(cursor, tabellenname):
    cursor.execute(f"PRAGMA table_info({tabellenname})")
    return {
        spalte[1]
        for spalte in cursor.fetchall()
    }


def _lizenzen_spalte_oder_standard(
    spalten,
    spaltenname,
    standard_sql,
):
    if spaltenname in spalten:
        return f"COALESCE({spaltenname}, '')"

    return standard_sql


def _lizenz_steuerdaten_laden(cursor, lizenz_id):
    """Lädt Steuerdaten und bleibt kompatibel zu älteren Testdatenbanken."""
    spalten = _tabellenspalten(cursor, "lizenzen")
    datenquelle = (
        "COALESCE(datenquelle, 'manuell')"
        if "datenquelle" in spalten
        else "'manuell'"
    )
    api_sync = (
        "COALESCE(api_sync_aktiv, 0)"
        if "api_sync_aktiv" in spalten
        else "0"
    )
    zuweisungsart = _lizenzen_spalte_oder_standard(
        spalten,
        "zuweisungsart",
        "''",
    )
    lizenzklasse = _lizenzen_spalte_oder_standard(
        spalten,
        "lizenzklasse",
        "''",
    )

    cursor.execute(
        f"""
        SELECT
            {datenquelle},
            {api_sync},
            {zuweisungsart},
            {lizenzklasse}
        FROM lizenzen
        WHERE id = ?
        """,
        (lizenz_id,),
    )

    return cursor.fetchone()


def entferne_lizenzzuweisung(benutzer_id, lizenz_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT id
        FROM zuweisungen
        WHERE benutzer_id = ?
          AND lizenz_id = ?
          AND status = 'aktiv'
    """, (benutzer_id, lizenz_id))

    zuweisung = cursor.fetchone()

    if zuweisung is None:
        verbindung.close()
        return False, "Für diesen Benutzer wurde keine aktive Zuweisung dieser Lizenz gefunden."

    cursor.execute("""
        UPDATE zuweisungen
        SET status = 'entfernt'
        WHERE id = ?
    """, (zuweisung[0],))

    verbindung.commit()
    verbindung.close()

    return True, "Lizenzzuweisung wurde entfernt."


def lizenz_ist_verfuegbar(cursor, lizenz_id):
    cursor.execute("""
        SELECT anzahl, anbieter, datenquelle
        FROM lizenzen
        WHERE id = ?
    """, (lizenz_id,))

    lizenz = cursor.fetchone()

    if lizenz is None:
        return False, "Diese Lizenz-ID existiert nicht."

    gesamt = lizenz[0] or 0
    anbieter = lizenz[1] or ""
    datenquelle = lizenz[2] or "manuell"

    # API-geführte Lizenzen können aus der Quelle kommen.
    # Die lokale Anzahl ist dann nicht immer führend.
    if anbieter == "Adobe" or datenquelle != "manuell":
        return True, ""

    cursor.execute("""
        SELECT COUNT(*)
        FROM zuweisungen
        WHERE lizenz_id = ? AND status = 'aktiv'
    """, (lizenz_id,))

    vergeben = cursor.fetchone()[0]

    if vergeben >= gesamt:
        return False, "Keine freie Lizenz mehr vorhanden."

    return True, ""


def lade_lizenzen_uebersicht():
    """
    Neue Übersicht passend zur vereinfachten Lizenzlogik.

    Rückgabe-Tuple bleibt bewusst kompatibel mit vielen alten Templates:
    0  id
    1  name
    2  anbieter
    3  anzahl
    4  lizenztyp
    5  kosten
    6  ablaufdatum
    7  verlaengerungsdatum
    8  lizenzklasse                    ALT
    9  zuweisungsart                   ALT
    10 kostenmodell
    11 technologiebereich              ALT
    12 kategorie_id
    13 kategorie_name
    14 kategorie_slug
    15 beschreibung                    NEU
    16 datenquelle                     NEU
    17 api_sync_aktiv                  NEU
    18 externe_id                      NEU
    19 status                          NEU
    20 kategorie_beschreibung          NEU
    21 kategorie_typische_nutzung      NEU
    22 externer_verbrauch              API
    23 verbrauch_gemeldet_am           API
    24 startdatum                      API
    25 externer_produktschluessel      API
    """
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute(
        """
        SELECT
            l.id,
            l.name,
            l.anbieter,
            COALESCE(l.anzahl, 0),
            l.lizenztyp,
            COALESCE(l.kosten, 0),
            l.ablaufdatum,
            l.verlaengerungsdatum,
            l.lizenzklasse,
            l.zuweisungsart,
            l.kostenmodell,
            l.technologiebereich,
            l.kategorie_id,
            k.name AS kategorie_name,
            k.slug AS kategorie_slug,
            l.beschreibung,
            COALESCE(l.datenquelle, 'manuell'),
            COALESCE(l.api_sync_aktiv, 0),
            l.externe_id,
            COALESCE(l.status, 'aktiv'),
            k.beschreibung AS kategorie_beschreibung,
            k.typische_nutzung AS kategorie_typische_nutzung,
            l.externer_verbrauch,
            l.verbrauch_gemeldet_am,
            l.startdatum,
            l.externer_produktschluessel
        FROM lizenzen l
        LEFT JOIN lizenz_kategorien k
            ON l.kategorie_id = k.id
        ORDER BY l.id DESC
        """
    )

    lizenzen = cursor.fetchall()
    verbindung.close()

    return lizenzen


def lade_lizenzuebersicht():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            l.id,
            l.name,
            l.anbieter,
            COALESCE(l.anzahl, 0) AS gesamt,
            COALESCE(l.kosten, 0),
            COALESCE(
                l.externer_verbrauch,
                COALESCE(b.anzahl, 0) + COALESCE(g.anzahl, 0)
            ) AS vergeben
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
        ORDER BY l.name
    """)

    daten = cursor.fetchall()
    verbindung.close()

    formatierte_daten = []

    for eintrag in daten:
        lizenz_id = eintrag[0]
        name = eintrag[1]
        anbieter = eintrag[2]
        gesamt = eintrag[3] or 0
        kosten = eintrag[4] or 0
        vergeben = eintrag[5] or 0
        frei = max(0, gesamt - vergeben)
        status = "OK" if gesamt >= vergeben else "ÜBERBUCHT"
        gesamtkosten = gesamt * kosten

        formatierte_daten.append((
            lizenz_id,
            name,
            anbieter,
            gesamt,
            vergeben,
            frei,
            status,
            f"{gesamtkosten:.2f} EUR"
        ))

    return formatierte_daten


def lade_kostenuebersicht():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            l.id,
            l.name,
            l.anbieter,
            COALESCE(l.anzahl, 0) AS anzahl,
            COALESCE(l.kosten, 0)
        FROM lizenzen l
        ORDER BY l.name
    """)

    daten = cursor.fetchall()
    verbindung.close()

    formatierte_daten = []
    gesamtsumme = 0

    for eintrag in daten:
        lizenz_id = eintrag[0]
        name = eintrag[1]
        anbieter = eintrag[2]
        anzahl = eintrag[3] or 0
        kosten = eintrag[4] or 0
        summe = anzahl * kosten
        gesamtsumme += summe

        formatierte_daten.append(
            (lizenz_id, name, anbieter, anzahl, f"{kosten:.2f} EUR", f"{summe:.2f} EUR")
        )

    return {
        "daten": formatierte_daten,
        "gesamtsumme": gesamtsumme
    }


def loesche_lizenz_mit_zuweisungen(lizenz_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        DELETE FROM zuweisungen
        WHERE lizenz_id = ?
    """, (lizenz_id,))

    cursor.execute("""
        DELETE FROM lizenz_zuweisungen
        WHERE lizenz_id = ?
    """, (lizenz_id,))

    cursor.execute("""
        DELETE FROM lizenz_erkennungsregeln
        WHERE lizenz_id = ?
    """, (lizenz_id,))

    # Erkannte Gruppen bleiben erhalten, werden aber wieder
    # zu offenen beziehungsweise neu zuordenbaren Gruppen.
    cursor.execute("""
        UPDATE gruppen_mapping
        SET
            lizenz_id = NULL,
            aktualisiert_am = CURRENT_TIMESTAMP
        WHERE lizenz_id = ?
    """, (lizenz_id,))

    cursor.execute("""
        DELETE FROM lizenzen
        WHERE id = ?
    """, (lizenz_id,))

    geloescht = cursor.rowcount

    verbindung.commit()
    verbindung.close()

    return geloescht


def aktualisiere_lizenz_kosten(lizenz_id, kosten):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        UPDATE lizenzen
        SET kosten = ?
        WHERE id = ?
    """, (kosten, lizenz_id))

    geaendert = cursor.rowcount

    verbindung.commit()
    verbindung.close()

    return geaendert


def weise_lizenz_zu(benutzer_id, lizenz_id, quelle="manuell", externe_id=None):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    lizenz_info = _lizenz_steuerdaten_laden(
        cursor,
        lizenz_id,
    )

    if lizenz_info is None:
        verbindung.close()
        return False, "Die ausgewählte Lizenz existiert nicht."

    datenquelle = lizenz_info[0]
    api_sync_aktiv = lizenz_info[1]
    zielart = _lizenz_zielart_aus_zeile(
        lizenz_info[2],
        lizenz_info[3],
    )

    if zielart != "benutzer":
        verbindung.close()
        return (
            False,
            "Diese Lizenz ist nicht personenbezogen und kann "
            "daher keinem Benutzer zugewiesen werden.",
        )

    if datenquelle != "manuell" and api_sync_aktiv == 1 and quelle == "manuell":
        verbindung.close()
        return False, "Diese Lizenz wird über eine Datenquelle/API synchronisiert. Manuelle Zuweisungen sind dafür nicht vorgesehen."

    cursor.execute("""
        SELECT COUNT(*)
        FROM zuweisungen
        WHERE benutzer_id = ?
          AND lizenz_id = ?
          AND status = 'aktiv'
    """, (benutzer_id, lizenz_id))

    bereits_aktiv = cursor.fetchone()[0]

    if bereits_aktiv > 0:
        verbindung.close()
        return False, "Dieser Benutzer hat diese Lizenz bereits aktiv zugewiesen."

    verfuegbar, meldung = lizenz_ist_verfuegbar(cursor, lizenz_id)

    if not verfuegbar:
        verbindung.close()
        return False, meldung

    cursor.execute("""
        SELECT COUNT(*)
        FROM zuweisungen
        WHERE benutzer_id = ?
          AND lizenz_id = ?
          AND status != 'aktiv'
    """, (benutzer_id, lizenz_id))

    alte_zuweisung = cursor.fetchone()[0]

    if alte_zuweisung > 0:
        cursor.execute("""
            UPDATE zuweisungen
            SET
                status = 'aktiv',
                zuweisungsdatum = DATE('now')
            WHERE benutzer_id = ?
              AND lizenz_id = ?
        """, (benutzer_id, lizenz_id))
    else:
        cursor.execute("""
            INSERT INTO zuweisungen
                (benutzer_id, lizenz_id, zuweisungsdatum, status)
            VALUES
                (?, ?, DATE('now'), 'aktiv')
        """, (benutzer_id, lizenz_id))

    # Parallel in neuer flexibler Zuweisungstabelle speichern.
    cursor.execute("""
        SELECT
            id,
            status
        FROM lizenz_zuweisungen
        WHERE lizenz_id = ?
          AND ziel_typ = 'benutzer'
          AND ziel_id = ?
        LIMIT 1
    """, (
        lizenz_id,
        benutzer_id,
    ))

    flexible_zuweisung = cursor.fetchone()

    if flexible_zuweisung is None:
        cursor.execute("""
            INSERT INTO lizenz_zuweisungen (
                lizenz_id,
                ziel_typ,
                ziel_id,
                zuweisungsdatum,
                status,
                quelle,
                externe_id,
                synchronisiert_am,
                entfernt_am
            )
            VALUES (
                ?,
                'benutzer',
                ?,
                DATE('now'),
                'aktiv',
                ?,
                ?,
                DATETIME('now'),
                NULL
            )
        """, (
            lizenz_id,
            benutzer_id,
            quelle,
            externe_id,
        ))

    elif str(
        flexible_zuweisung[1] or ""
    ).strip().lower() != "aktiv":
        cursor.execute("""
            UPDATE lizenz_zuweisungen
            SET
                status = 'aktiv',
                zuweisungsdatum = DATE('now'),
                quelle = ?,
                externe_id = ?,
                synchronisiert_am = DATETIME('now'),
                entfernt_am = NULL
            WHERE id = ?
        """, (
            quelle,
            externe_id,
            flexible_zuweisung[0],
        ))

    elif quelle != "manuell":
        cursor.execute("""
            UPDATE lizenz_zuweisungen
            SET
                quelle = ?,
                externe_id = ?,
                synchronisiert_am = DATETIME('now'),
                entfernt_am = NULL
            WHERE id = ?
        """, (
            quelle,
            externe_id,
            flexible_zuweisung[0],
        ))

    verbindung.commit()
    verbindung.close()

    return True, "Lizenz wurde erfolgreich zugewiesen."


def lizenz_hinzufuegen(
    name,
    anbieter,
    anzahl,
    lizenztyp=None,
    kosten=0,
    ablaufdatum=None,
    verlaengerungsdatum=None,
    lizenzklasse="benutzer",
    zuweisungsart="benutzer",
    kostenmodell="fortlaufend",
    technologiebereich="allgemein",
    kategorie_id=None,
    lizenzmodell_id=None,
    zuweisungszieltyp_id=None,
    beschreibung="",
    datenquelle="manuell",
    datenquelle_id=None,
    api_sync_aktiv=0,
    externe_id=None,
    status="aktiv",
):
    """
    Neue Hauptfunktion zum Hinzufügen einer Lizenz.

    Lizenzmodell und Zuweisungszieltyp bleiben als optionale Parameter nur aus
    Kompatibilitätsgründen bestehen, werden in der neuen UI aber nicht mehr genutzt.
    """
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    name = bereinige_text(name)
    anbieter = bereinige_text(anbieter)
    beschreibung = bereinige_text(beschreibung)
    datenquelle = bereinige_text(datenquelle, "manuell") or "manuell"

    try:
        datenquelle_id = (
            int(datenquelle_id)
            if datenquelle_id not in (None, "")
            else None
        )
    except (TypeError, ValueError):
        datenquelle_id = None

    if datenquelle_id is not None:
        cursor.execute(
            """
            SELECT typ
            FROM datenquellen
            WHERE id = ? AND aktiv = 1
            """,
            (datenquelle_id,),
        )
        datenquelle_eintrag = cursor.fetchone()

        if datenquelle_eintrag is not None:
            datenquelle = bereinige_text(
                datenquelle_eintrag[0],
                "manuell",
            ) or "manuell"
            api_sync_aktiv = 1
        else:
            datenquelle = "manuell"
            datenquelle_id = None
            api_sync_aktiv = 0

    externe_id = bereinige_text(externe_id)
    status = bereinige_text(status, "aktiv") or "aktiv"

    anzahl = bereinige_int(anzahl, 0)
    kosten = bereinige_float(kosten, 0.0)
    api_sync_aktiv = bereinige_bool_int(api_sync_aktiv)

    if not lizenztyp:
        lizenztyp = name

    cursor.execute(
        """
        INSERT INTO lizenzen (
            name,
            anbieter,
            beschreibung,
            anzahl,
            lizenztyp,
            kosten,
            ablaufdatum,
            verlaengerungsdatum,
            lizenzklasse,
            zuweisungsart,
            kostenmodell,
            technologiebereich,
            kategorie_id,
            lizenzmodell_id,
            zuweisungszieltyp_id,
            datenquelle,
            datenquelle_id,
            api_sync_aktiv,
            externe_id,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            anbieter,
            beschreibung,
            anzahl,
            lizenztyp,
            kosten,
            ablaufdatum,
            verlaengerungsdatum,
            lizenzklasse,
            zuweisungsart,
            kostenmodell,
            technologiebereich,
            kategorie_id,
            lizenzmodell_id,
            zuweisungszieltyp_id,
            datenquelle,
            datenquelle_id,
            api_sync_aktiv,
            externe_id,
            status,
        )
    )

    verbindung.commit()
    neue_lizenz_id = cursor.lastrowid
    verbindung.close()

    return neue_lizenz_id


def lade_lizenz_details(lizenz_id):
    """
    Detaildaten passend zur neuen Logik.

    Rückgabe-Tuple:
    0  id
    1  name
    2  anbieter
    3  anzahl
    4  lizenztyp
    5  kosten
    6  ablaufdatum
    7  verlaengerungsdatum
    8  lizenzklasse                 ALT
    9  zuweisungsart                ALT
    10 kostenmodell
    11 technologiebereich           ALT
    12 kategorie_id
    13 kategorie_name
    14 kategorie_slug
    15 kategorie_beschreibung
    16 kategorie_typische_nutzung
    17 beschreibung                 NEU
    18 datenquelle                  NEU
    19 api_sync_aktiv               NEU
    20 externe_id                   NEU
    21 status                       NEU
    22 datenquelle_id               NEU
    23 externer_verbrauch           API
    24 verbrauch_gemeldet_am        API
    25 startdatum                   API
    26 externer_produktschluessel   API
    """
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT
            l.id,
            l.name,
            l.anbieter,
            COALESCE(l.anzahl, 0),
            l.lizenztyp,
            COALESCE(l.kosten, 0),
            l.ablaufdatum,
            l.verlaengerungsdatum,
            l.lizenzklasse,
            l.zuweisungsart,
            l.kostenmodell,
            l.technologiebereich,
            l.kategorie_id,
            k.name AS kategorie_name,
            k.slug AS kategorie_slug,
            k.beschreibung AS kategorie_beschreibung,
            k.typische_nutzung AS kategorie_typische_nutzung,
            l.beschreibung,
            COALESCE(l.datenquelle, 'manuell'),
            COALESCE(l.api_sync_aktiv, 0),
            l.externe_id,
            COALESCE(l.status, 'aktiv'),
            l.datenquelle_id,
            l.externer_verbrauch,
            l.verbrauch_gemeldet_am,
            l.startdatum,
            l.externer_produktschluessel
        FROM lizenzen l
        LEFT JOIN lizenz_kategorien k
            ON l.kategorie_id = k.id
        WHERE l.id = ?
    """, (lizenz_id,))

    lizenz = cursor.fetchone()

    cursor.execute("""
        SELECT
            b.id,
            b.name,
            b.benutzername,
            b.email,
            b.abteilung,
            z.zuweisungsdatum,
            z.status
        FROM zuweisungen z
        JOIN benutzer b ON z.benutzer_id = b.id
        WHERE z.lizenz_id = ?
          AND z.status = 'aktiv'
        ORDER BY b.name
    """, (lizenz_id,))

    aktive_benutzer = cursor.fetchall()

    cursor.execute("""
        SELECT
            b.id,
            b.name,
            b.benutzername,
            b.email,
            b.abteilung,
            z.zuweisungsdatum,
            z.status
        FROM zuweisungen z
        JOIN benutzer b ON z.benutzer_id = b.id
        WHERE z.lizenz_id = ?
          AND z.status != 'aktiv'
        ORDER BY z.zuweisungsdatum DESC, b.name
    """, (lizenz_id,))

    entfernte_benutzer = cursor.fetchall()

    verbindung.close()

    return lizenz, aktive_benutzer, entfernte_benutzer


def lizenz_loeschen(lizenz_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM zuweisungen
            WHERE lizenz_id = ?
            """,
            (lizenz_id,),
        )

        cursor.execute(
            """
            DELETE FROM lizenz_zuweisungen
            WHERE lizenz_id = ?
            """,
            (lizenz_id,),
        )

        cursor.execute(
            """
            DELETE FROM lizenz_erkennungsregeln
            WHERE lizenz_id = ?
            """,
            (lizenz_id,),
        )

        cursor.execute(
            """
            UPDATE gruppen_mapping
            SET
                lizenz_id = NULL,
                aktualisiert_am = CURRENT_TIMESTAMP
            WHERE lizenz_id = ?
            """,
            (lizenz_id,),
        )

        cursor.execute(
            """
            DELETE FROM lizenzen
            WHERE id = ?
            """,
            (lizenz_id,),
        )

        verbindung.commit()

    except Exception:
        verbindung.rollback()
        raise

    finally:
        verbindung.close()


def lizenz_aktualisieren(
    lizenz_id,
    name,
    anbieter,
    anzahl,
    lizenztyp=None,
    kosten=0,
    ablaufdatum=None,
    verlaengerungsdatum=None,
    lizenzklasse="benutzer",
    zuweisungsart="benutzer",
    kostenmodell="fortlaufend",
    technologiebereich="allgemein",
    kategorie_id=None,
    lizenzmodell_id=None,
    zuweisungszieltyp_id=None,
    beschreibung="",
    datenquelle="manuell",
    datenquelle_id=None,
    api_sync_aktiv=0,
    externe_id=None,
    status="aktiv",
):
    """
    Neue Aktualisierungsfunktion.

    Alte Parameter bleiben nur aus Kompatibilitätsgründen enthalten.
    """
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    name = bereinige_text(name)
    anbieter = bereinige_text(anbieter)
    beschreibung = bereinige_text(beschreibung)
    datenquelle = bereinige_text(datenquelle, "manuell") or "manuell"

    try:
        datenquelle_id = (
            int(datenquelle_id)
            if datenquelle_id not in (None, "")
            else None
        )
    except (TypeError, ValueError):
        datenquelle_id = None

    if datenquelle_id is not None:
        cursor.execute(
            """
            SELECT typ
            FROM datenquellen
            WHERE id = ? AND aktiv = 1
            """,
            (datenquelle_id,),
        )
        datenquelle_eintrag = cursor.fetchone()

        if datenquelle_eintrag is not None:
            datenquelle = bereinige_text(
                datenquelle_eintrag[0],
                "manuell",
            ) or "manuell"
            api_sync_aktiv = 1
        else:
            datenquelle = "manuell"
            datenquelle_id = None
            api_sync_aktiv = 0

    externe_id = bereinige_text(externe_id)
    status = bereinige_text(status, "aktiv") or "aktiv"

    anzahl = bereinige_int(anzahl, 0)
    kosten = bereinige_float(kosten, 0.0)
    api_sync_aktiv = bereinige_bool_int(api_sync_aktiv)

    if not lizenztyp:
        lizenztyp = name

    cursor.execute("""
        UPDATE lizenzen
        SET
            name = ?,
            anbieter = ?,
            beschreibung = ?,
            anzahl = ?,
            lizenztyp = ?,
            kosten = ?,
            ablaufdatum = ?,
            verlaengerungsdatum = ?,
            lizenzklasse = ?,
            zuweisungsart = ?,
            kostenmodell = ?,
            technologiebereich = ?,
            kategorie_id = ?,
            lizenzmodell_id = ?,
            zuweisungszieltyp_id = ?,
            datenquelle = ?,
            datenquelle_id = ?,
            api_sync_aktiv = ?,
            externe_id = ?,
            status = ?
        WHERE id = ?
    """, (
        name,
        anbieter,
        beschreibung,
        anzahl,
        lizenztyp,
        kosten,
        ablaufdatum,
        verlaengerungsdatum,
        lizenzklasse,
        zuweisungsart,
        kostenmodell,
        technologiebereich,
        kategorie_id,
        lizenzmodell_id,
        zuweisungszieltyp_id,
        datenquelle,
        datenquelle_id,
        api_sync_aktiv,
        externe_id,
        status,
        lizenz_id
    ))

    verbindung.commit()
    verbindung.close()


def sync_lizenzzuweisung_speichern(lizenz_id, benutzer_id, quelle, externe_id=None):
    """
    Speichert eine von einer Datenquelle gelieferte Benutzerzuweisung.

    Bereits aktive manuelle Zuweisungen werden nicht von einer Datenquelle
    übernommen. Von derselben Quelle verwaltete Zuweisungen werden dagegen
    bei jedem Lauf aufgefrischt und bei Bedarf reaktiviert.
    """
    quelle = bereinige_text(quelle)

    if not quelle or quelle == "manuell":
        return weise_lizenz_zu(
            benutzer_id=benutzer_id,
            lizenz_id=lizenz_id,
            quelle="manuell",
            externe_id=externe_id,
        )

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    try:
        verbindung.execute("BEGIN IMMEDIATE")

        lizenz = _lizenz_steuerdaten_laden(
            cursor,
            lizenz_id,
        )

        if lizenz is None:
            verbindung.rollback()
            return False, "Die ausgewählte Lizenz existiert nicht."

        zielart = _lizenz_zielart_aus_zeile(
            lizenz[2],
            lizenz[3],
        )

        if zielart != "benutzer":
            verbindung.rollback()
            return (
                False,
                "Diese Lizenz ist nicht personenbezogen und wird "
                "deshalb nicht als Benutzerzuweisung gespeichert.",
            )

        cursor.execute(
            """
            SELECT id, status
            FROM zuweisungen
            WHERE benutzer_id = ?
              AND lizenz_id = ?
            LIMIT 1
            """,
            (benutzer_id, lizenz_id),
        )
        alte_zuweisung = cursor.fetchone()
        bereits_aktiv = bool(
            alte_zuweisung
            and str(alte_zuweisung[1] or "").strip().lower() == "aktiv"
        )

        cursor.execute(
            """
            SELECT id, status, COALESCE(quelle, 'manuell')
            FROM lizenz_zuweisungen
            WHERE lizenz_id = ?
              AND ziel_typ = 'benutzer'
              AND ziel_id = ?
            LIMIT 1
            """,
            (lizenz_id, benutzer_id),
        )
        flexible_zuweisung = cursor.fetchone()

        if bereits_aktiv:
            if (
                flexible_zuweisung is not None
                and str(flexible_zuweisung[2] or "").strip() == quelle
            ):
                cursor.execute(
                    """
                    UPDATE lizenz_zuweisungen
                    SET
                        status = 'aktiv',
                        externe_id = ?,
                        synchronisiert_am = DATETIME('now'),
                        entfernt_am = NULL
                    WHERE id = ?
                    """,
                    (externe_id, flexible_zuweisung[0]),
                )

            verbindung.commit()
            return True, "Die Lizenzzuweisung ist bereits aktiv."

        verfuegbar, meldung = lizenz_ist_verfuegbar(cursor, lizenz_id)

        if not verfuegbar:
            verbindung.rollback()
            return False, meldung

        if alte_zuweisung is None:
            cursor.execute(
                """
                INSERT INTO zuweisungen (
                    benutzer_id,
                    lizenz_id,
                    zuweisungsdatum,
                    status
                )
                VALUES (?, ?, DATE('now'), 'aktiv')
                """,
                (benutzer_id, lizenz_id),
            )
        else:
            cursor.execute(
                """
                UPDATE zuweisungen
                SET
                    status = 'aktiv',
                    zuweisungsdatum = DATE('now')
                WHERE id = ?
                """,
                (alte_zuweisung[0],),
            )

        if flexible_zuweisung is None:
            cursor.execute(
                """
                INSERT INTO lizenz_zuweisungen (
                    lizenz_id,
                    ziel_typ,
                    ziel_id,
                    zuweisungsdatum,
                    status,
                    quelle,
                    externe_id,
                    synchronisiert_am,
                    entfernt_am
                )
                VALUES (
                    ?, 'benutzer', ?, DATE('now'), 'aktiv',
                    ?, ?, DATETIME('now'), NULL
                )
                """,
                (lizenz_id, benutzer_id, quelle, externe_id),
            )
        else:
            cursor.execute(
                """
                UPDATE lizenz_zuweisungen
                SET
                    status = 'aktiv',
                    zuweisungsdatum = DATE('now'),
                    quelle = ?,
                    externe_id = ?,
                    synchronisiert_am = DATETIME('now'),
                    entfernt_am = NULL
                WHERE id = ?
                """,
                (quelle, externe_id, flexible_zuweisung[0]),
            )

        verbindung.commit()
        return True, "Lizenz wurde erfolgreich zugewiesen."

    except Exception:
        verbindung.rollback()
        raise

    finally:
        verbindung.close()


def sync_lizenzzuweisung_ziel_speichern(
    lizenz_id,
    ziel_typ,
    ziel_id,
    quelle,
    externe_id=None,
):
    """Speichert eine externe Zuweisung an ein Gerät oder einen Server.

    Benutzer bleiben wegen der kompatiblen ``zuweisungen``-Tabelle in der
    bestehenden Benutzerfunktion. Andere Ziele werden ausschließlich in der
    flexiblen Zuweisungstabelle geführt.
    """
    ziel_typ = bereinige_text(ziel_typ).lower()
    quelle = bereinige_text(quelle)

    if ziel_typ == "benutzer":
        return sync_lizenzzuweisung_speichern(
            lizenz_id,
            ziel_id,
            quelle,
            externe_id,
        )

    if ziel_typ not in {"geraet", "server"}:
        return False, "Ungültiger Zieltyp für die Lizenzzuweisung."

    if not quelle or quelle == "manuell":
        return weise_lizenz_an_ziel_zu(lizenz_id, ziel_typ, ziel_id)

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    try:
        verbindung.execute("BEGIN IMMEDIATE")

        zieltabelle = "geraete" if ziel_typ == "geraet" else "server"
        if cursor.execute(
            "SELECT id FROM lizenzen WHERE id = ?",
            (lizenz_id,),
        ).fetchone() is None:
            verbindung.rollback()
            return False, "Die ausgewählte Lizenz existiert nicht."

        if cursor.execute(
            f"SELECT id FROM {zieltabelle} WHERE id = ?",
            (ziel_id,),
        ).fetchone() is None:
            verbindung.rollback()
            return False, "Das Zuweisungsziel existiert nicht."

        vorhanden = cursor.execute(
            """
            SELECT id, status, COALESCE(quelle, 'manuell')
            FROM lizenz_zuweisungen
            WHERE lizenz_id = ?
              AND ziel_typ = ?
              AND ziel_id = ?
            LIMIT 1
            """,
            (lizenz_id, ziel_typ, ziel_id),
        ).fetchone()
        war_bereits_aktiv = bool(
            vorhanden and vorhanden[1] == "aktiv"
        )

        if vorhanden and vorhanden[2] == "manuell" and vorhanden[1] == "aktiv":
            verbindung.commit()
            return True, "Die manuelle Lizenzzuweisung bleibt aktiv."

        if vorhanden is None:
            cursor.execute(
                """
                INSERT INTO lizenz_zuweisungen (
                    lizenz_id, ziel_typ, ziel_id, zuweisungsdatum,
                    status, quelle, externe_id, synchronisiert_am, entfernt_am
                )
                VALUES (?, ?, ?, DATE('now'), 'aktiv', ?, ?, DATETIME('now'), NULL)
                """,
                (lizenz_id, ziel_typ, ziel_id, quelle, externe_id),
            )
        else:
            cursor.execute(
                """
                UPDATE lizenz_zuweisungen
                SET status = 'aktiv',
                    zuweisungsdatum = DATE('now'),
                    quelle = ?,
                    externe_id = ?,
                    synchronisiert_am = DATETIME('now'),
                    entfernt_am = NULL
                WHERE id = ?
                """,
                (quelle, externe_id, vorhanden[0]),
            )

        verbindung.commit()
        if war_bereits_aktiv:
            return True, "Die Lizenzzuweisung war bereits aktiv."

        return True, "Lizenz wurde erfolgreich zugewiesen."
    except Exception:
        verbindung.rollback()
        raise
    finally:
        verbindung.close()


def weise_lizenz_an_ziel_zu(lizenz_id, ziel_typ, ziel_id):
    """
    Alte flexible Geräte-/Server-Zuweisung bleibt erhalten,
    wird aber nicht mehr als Hauptlogik betrachtet.
    """
    erlaubte_zieltypen = ["benutzer", "geraet", "server"]

    if ziel_typ not in erlaubte_zieltypen:
        return False, "Ungültiger Zieltyp für die Lizenzzuweisung."

    if ziel_typ == "benutzer":
        return weise_lizenz_zu(
            benutzer_id=ziel_id,
            lizenz_id=lizenz_id,
            quelle="manuell",
        )

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT COALESCE(anzahl, 0)
        FROM lizenzen
        WHERE id = ?
    """, (lizenz_id,))

    lizenz = cursor.fetchone()

    if lizenz is None:
        verbindung.close()
        return False, "Die ausgewählte Lizenz existiert nicht."

    gesamt = lizenz[0] or 0

    cursor.execute("""
        SELECT COUNT(*)
        FROM lizenz_zuweisungen
        WHERE lizenz_id = ?
          AND ziel_typ = ?
          AND ziel_id = ?
          AND status = 'aktiv'
    """, (lizenz_id, ziel_typ, ziel_id))

    bereits_aktiv = cursor.fetchone()[0]

    if bereits_aktiv > 0:
        verbindung.close()
        return False, "Diese Lizenz ist diesem Ziel bereits aktiv zugewiesen."

    cursor.execute("""
        SELECT COUNT(*)
        FROM lizenz_zuweisungen
        WHERE lizenz_id = ?
          AND status = 'aktiv'
    """, (lizenz_id,))

    vergeben = cursor.fetchone()[0]

    if vergeben >= gesamt:
        verbindung.close()
        return False, "Keine freie Lizenz mehr vorhanden."

    cursor.execute("""
        SELECT COUNT(*)
        FROM lizenz_zuweisungen
        WHERE lizenz_id = ?
          AND ziel_typ = ?
          AND ziel_id = ?
          AND status != 'aktiv'
    """, (lizenz_id, ziel_typ, ziel_id))

    alte_zuweisung = cursor.fetchone()[0]

    if alte_zuweisung > 0:
        cursor.execute("""
            UPDATE lizenz_zuweisungen
            SET
                status = 'aktiv',
                zuweisungsdatum = DATE('now'),
                quelle = 'manuell',
                synchronisiert_am = NULL
            WHERE lizenz_id = ?
              AND ziel_typ = ?
              AND ziel_id = ?
        """, (lizenz_id, ziel_typ, ziel_id))
    else:
        cursor.execute("""
            INSERT INTO lizenz_zuweisungen
                (lizenz_id, ziel_typ, ziel_id, zuweisungsdatum, status, quelle)
            VALUES
                (?, ?, ?, DATE('now'), 'aktiv', 'manuell')
        """, (lizenz_id, ziel_typ, ziel_id))

    verbindung.commit()
    verbindung.close()

    return True, "Lizenz wurde erfolgreich zugewiesen."


def lade_lizenz_ziele(lizenz_id, ziel_typ):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    if ziel_typ == "server":
        cursor.execute("""
            SELECT
                s.id,
                s.name,
                s.hostname,
                s.ip_adresse,
                s.betriebssystem,
                lz.zuweisungsdatum,
                lz.status
            FROM lizenz_zuweisungen lz
            JOIN server s ON lz.ziel_id = s.id
            WHERE lz.lizenz_id = ?
              AND lz.ziel_typ = 'server'
              AND lz.status = 'aktiv'
            ORDER BY s.name
        """, (lizenz_id,))

        daten = cursor.fetchall()
        verbindung.close()
        return daten

    if ziel_typ == "geraet":
        cursor.execute("""
            SELECT
                g.id,
                g.name,
                g.inventarnummer,
                g.seriennummer,
                g.geraetetyp,
                lz.zuweisungsdatum,
                lz.status
            FROM lizenz_zuweisungen lz
            JOIN geraete g ON lz.ziel_id = g.id
            WHERE lz.lizenz_id = ?
              AND lz.ziel_typ = 'geraet'
              AND lz.status = 'aktiv'
            ORDER BY g.name
        """, (lizenz_id,))

        daten = cursor.fetchall()
        verbindung.close()
        return daten

    verbindung.close()
    return []


def entferne_lizenzzuweisung_flexibel(lizenz_id, ziel_typ, ziel_id):
    erlaubte_zieltypen = ["benutzer", "geraet", "server"]

    if ziel_typ not in erlaubte_zieltypen:
        return False, "Ungültiger Zieltyp."

    if ziel_typ == "benutzer":
        return entferne_lizenzzuweisung(
            ziel_id,
            lizenz_id,
        )

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT id
        FROM lizenz_zuweisungen
        WHERE lizenz_id = ?
          AND ziel_typ = ?
          AND ziel_id = ?
          AND status = 'aktiv'
    """, (lizenz_id, ziel_typ, ziel_id))

    zuweisung = cursor.fetchone()

    if zuweisung is None:
        verbindung.close()
        return False, "Keine aktive Zuweisung gefunden."

    cursor.execute("""
        UPDATE lizenz_zuweisungen
        SET
            status = 'entfernt',
            entfernt_am = DATE('now')
        WHERE lizenz_id = ?
          AND ziel_typ = ?
          AND ziel_id = ?
          AND status = 'aktiv'
    """, (lizenz_id, ziel_typ, ziel_id))

    verbindung.commit()
    verbindung.close()

    return True, "Lizenzzuweisung wurde entfernt."


def lade_entfernte_lizenz_ziele(lizenz_id, ziel_typ):
    erlaubte_zieltypen = ["geraet", "server"]

    if ziel_typ not in erlaubte_zieltypen:
        return []

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    if ziel_typ == "server":
        cursor.execute("""
            SELECT
                s.id,
                s.name,
                s.hostname,
                s.ip_adresse,
                s.betriebssystem,
                lz.zuweisungsdatum,
                lz.status
            FROM lizenz_zuweisungen lz
            JOIN server s ON s.id = lz.ziel_id
            WHERE lz.lizenz_id = ?
              AND lz.ziel_typ = 'server'
              AND lz.status = 'entfernt'
            ORDER BY lz.zuweisungsdatum DESC
        """, (lizenz_id,))

    else:
        cursor.execute("""
            SELECT
                g.id,
                g.name,
                g.inventarnummer,
                g.seriennummer,
                g.geraetetyp,
                lz.zuweisungsdatum,
                lz.status
            FROM lizenz_zuweisungen lz
            JOIN geraete g ON g.id = lz.ziel_id
            WHERE lz.lizenz_id = ?
              AND lz.ziel_typ = 'geraet'
              AND lz.status = 'entfernt'
            ORDER BY lz.zuweisungsdatum DESC
        """, (lizenz_id,))

    eintraege = cursor.fetchall()
    verbindung.close()

    return eintraege
