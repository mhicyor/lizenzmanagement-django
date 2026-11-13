from demo.database import connect as demo_connection
import os
import sqlite3
from datetime import datetime

from benutzer_status_service import (
    MANUELL_DEAKTIVIERT,
    NICHT_IM_AD_GEFUNDEN,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "lizenzmanagement.db")


def verbindung_oeffnen():
    verbindung = demo_connection(DB_NAME)
    verbindung.execute("PRAGMA foreign_keys = ON")
    return verbindung


def datum_ist_gueltig(datum_text):
    if datum_text == "":
        return True

    try:
        datetime.strptime(datum_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def spalte_hinzufuegen_wenn_fehlt(cursor, tabellenname, spaltenname, definition):
    cursor.execute(f"PRAGMA table_info({tabellenname})")
    vorhandene_spalten = [spalte[1] for spalte in cursor.fetchall()]

    if spaltenname not in vorhandene_spalten:
        cursor.execute(
            f"ALTER TABLE {tabellenname} ADD COLUMN {spaltenname} {definition}"
        )


def standard_anbieter_anlegen(cursor):
    standard_anbieter = [
        {
            "name": "Adobe",
            "beschreibung": "Anbieter für Adobe Creative Cloud, Acrobat und weitere Adobe-Produkte.",
            "webseite": "https://www.adobe.com",
        },
        {
            "name": "Microsoft",
            "beschreibung": "Anbieter für Microsoft 365, Windows, Server- und Cloud-Produkte.",
            "webseite": "https://www.microsoft.com",
        },
        {
            "name": "Sophos",
            "beschreibung": "Anbieter für Endpoint Security, Firewall und Sicherheitslösungen.",
            "webseite": "https://www.sophos.com",
        },
        {
            "name": "Jamf",
            "beschreibung": "Anbieter für Apple-Geräteverwaltung und MDM-Lösungen.",
            "webseite": "https://www.jamf.com",
        },
        {
            "name": "Zoom",
            "beschreibung": "Anbieter für Videokonferenz- und Kommunikationslösungen.",
            "webseite": "https://www.zoom.com",
        },
        {
            "name": "DeepL",
            "beschreibung": "Anbieter für Übersetzungs- und KI-Sprachdienste.",
            "webseite": "https://www.deepl.com",
        },
        {
            "name": "OpenAI",
            "beschreibung": "Anbieter für KI- und API-basierte Dienste.",
            "webseite": "https://openai.com",
        },
        {
            "name": "VMware",
            "beschreibung": "Anbieter für Virtualisierung und Infrastruktur-Software.",
            "webseite": "https://www.vmware.com",
        },
        {
            "name": "JetBrains",
            "beschreibung": "Anbieter für Entwicklungsumgebungen und Entwicklerwerkzeuge.",
            "webseite": "https://www.jetbrains.com",
        },
        {
            "name": "Atlassian",
            "beschreibung": "Anbieter für Jira, Confluence und weitere Kollaborationstools.",
            "webseite": "https://www.atlassian.com",
        },
    ]

    for anbieter in standard_anbieter:
        cursor.execute(
            """
            SELECT id
            FROM anbieter
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
            """,
            (anbieter["name"],)
        )

        vorhandener_anbieter = cursor.fetchone()

        # Der Bootstrap legt nur fehlende Standardwerte an. Bereits
        # vorhandene Anbieter koennen in der Anwendung bewusst angepasst
        # oder deaktiviert worden sein und duerfen deshalb nicht bei jedem
        # Start ueberschrieben beziehungsweise reaktiviert werden.
        if not vorhandener_anbieter:
            cursor.execute(
                """
                INSERT INTO anbieter (
                    name,
                    beschreibung,
                    webseite,
                    aktiv,
                    erstellt_am,
                    aktualisiert_am
                )
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    anbieter["name"],
                    anbieter["beschreibung"],
                    anbieter["webseite"],
                )
            )


def standard_lizenzkategorien_anlegen(cursor):
    """
    Neue vereinfachte Kategorie-Logik.

    Die bisherigen Inhalte aus "Lizenzmodell" werden jetzt als Lizenzkategorien geführt.
    Dadurch entfallen separate Dropdowns für Lizenzmodell und Zuweisungszieltyp in der UI.

    Die Kategorie beschreibt nur noch die Art/Verwaltungslogik der Lizenz.
    Die konkrete Beschreibung steht später direkt an der Lizenz.
    Die konkrete Zuordnung erfolgt über Zuweisungen.
    """
    standard_kategorien = [
        {
            "name": "Nutzerbasierte Lizenz",
            "slug": "nutzerbasierte_lizenz",
            "beschreibung": "Lizenz, die typischerweise einem Benutzer, Account oder einer Person zugeordnet wird.",
            "typische_nutzung": "SaaS-Produkte, Microsoft 365, Adobe, personenbezogene Software oder Account-basierte Dienste.",
            "sortierung": 10,
        },
        {
            "name": "Gerätebasierte Lizenz",
            "slug": "geraetebasierte_lizenz",
            "beschreibung": "Lizenz, die typischerweise einem Gerät, Client, Endpoint oder Arbeitsplatzsystem zugeordnet wird.",
            "typische_nutzung": "Endpoint Security, Gerätesoftware, MDM, Client-Tools oder gerätebezogene Anwendungen.",
            "sortierung": 20,
        },
        {
            "name": "Infrastrukturbasierte Lizenz",
            "slug": "infrastrukturbasierte_lizenz",
            "beschreibung": "Lizenz für Server, virtuelle Maschinen, Instanzen, Dienste oder Infrastrukturkomponenten.",
            "typische_nutzung": "Windows Server, Datenbankserver, Backup-Systeme, virtuelle Maschinen oder Infrastruktur-Software.",
            "sortierung": 30,
        },
        {
            "name": "Verbrauchsbasierte Lizenz",
            "slug": "verbrauchsbasierte_lizenz",
            "beschreibung": "Lizenz, deren Nutzung über Verbrauch, Kontingente, Credits, Tokens oder API-Aufrufe betrachtet wird.",
            "typische_nutzung": "API-Nutzung, Übersetzungsvolumen, KI-Tokens, Credits oder nutzungsabhängige Dienste.",
            "sortierung": 40,
        },
        {
            "name": "Vertragsbasierte Lizenz",
            "slug": "vertragsbasierte_lizenz",
            "beschreibung": "Lizenz, die über Vertrag, Laufzeit, Wartung, Support oder Rahmenvereinbarung verwaltet wird.",
            "typische_nutzung": "Wartungsverträge, Supportverträge, Rahmenverträge oder organisationsbezogene Lizenzvereinbarungen.",
            "sortierung": 50,
        },
        {
            "name": "Poolbasierte Lizenz",
            "slug": "poolbasierte_lizenz",
            "beschreibung": "Lizenz, die als gemeinsames Kontingent oder Pool verwaltet wird.",
            "typische_nutzung": "Floating Licenses, Lizenzpools, gemeinsam genutzte Kontingente oder zentrale Softwarepools.",
            "sortierung": 60,
        },
    ]

    for kategorie in standard_kategorien:
        cursor.execute(
            """
            SELECT id
            FROM lizenz_kategorien
            WHERE slug = ? OR name = ?
            """,
            (
                kategorie["slug"],
                kategorie["name"],
            )
        )

        vorhandene_kategorie = cursor.fetchone()

        # Benutzerdefinierte Kategorien bleiben vollstaendig erhalten.
        # Ebenso wird eine bewusst archivierte Standardkategorie nicht
        # ungefragt reaktiviert. Damit ist die Initialisierung wiederholbar,
        # ohne Fachdaten zu veraendern.
        if not vorhandene_kategorie:
            cursor.execute(
                """
                INSERT INTO lizenz_kategorien (
                    name,
                    slug,
                    beschreibung,
                    typische_nutzung,
                    lizenzlogik,
                    typische_zuordnung,
                    interne_lizenzklasse,
                    standard_zuweisungsart,
                    aktiv,
                    archiviert,
                    archiviert_am,
                    archivierungsgrund,
                    sortierung,
                    erstellt_am,
                    aktualisiert_am
                )
                VALUES (?, ?, ?, ?, '', '', 'benutzer', 'benutzer', 1, 0, NULL, NULL, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    kategorie["name"],
                    kategorie["slug"],
                    kategorie["beschreibung"],
                    kategorie["typische_nutzung"],
                    kategorie["sortierung"],
                )
            )


def standard_lizenzmodelle_anlegen(cursor):
    """
    Alte Funktion bleibt aus Kompatibilitätsgründen erhalten.
    Nach neuer Roadmap wird sie aber nicht mehr in datenbank_erstellen() aufgerufen.
    """
    standard_modelle = [
        {
            "name": "Nutzerbasiert",
            "slug": "nutzerbasiert",
            "beschreibung": "Lizenz wird pro Benutzer oder Account gezählt und verwaltet.",
            "logik_typ": "nutzerbasiert",
            "sortierung": 10,
        },
        {
            "name": "Gerätebasiert",
            "slug": "geraetebasiert",
            "beschreibung": "Lizenz wird pro Gerät, Client oder Endpoint gezählt und verwaltet.",
            "logik_typ": "geraetebasiert",
            "sortierung": 20,
        },
        {
            "name": "Infrastrukturbasiert",
            "slug": "infrastrukturbasiert",
            "beschreibung": "Lizenz wird pro Server, Instanz, VM, Core oder Infrastruktur-System verwaltet.",
            "logik_typ": "infrastrukturbasiert",
            "sortierung": 30,
        },
        {
            "name": "Verbrauchsbasiert",
            "slug": "verbrauchsbasiert",
            "beschreibung": "Lizenz wird nach Verbrauch, Kontingent, Credits, Tokens oder API-Nutzung verwaltet.",
            "logik_typ": "verbrauchsbasiert",
            "sortierung": 40,
        },
        {
            "name": "Vertragsbasiert",
            "slug": "vertragsbasiert",
            "beschreibung": "Lizenz wird über Vertrag, Rahmenvereinbarung, Laufzeit oder Organisation verwaltet.",
            "logik_typ": "vertragsbasiert",
            "sortierung": 50,
        },
        {
            "name": "Poolbasiert",
            "slug": "poolbasiert",
            "beschreibung": "Lizenz wird als Pool, Floating License oder gleichzeitige Nutzung verwaltet.",
            "logik_typ": "poolbasiert",
            "sortierung": 60,
        },
    ]

    for modell in standard_modelle:
        cursor.execute(
            """
            SELECT id
            FROM lizenz_modelle
            WHERE slug = ? OR name = ?
            """,
            (
                modell["slug"],
                modell["name"],
            )
        )

        vorhandenes_modell = cursor.fetchone()

        if vorhandenes_modell:
            cursor.execute(
                """
                UPDATE lizenz_modelle
                SET
                    slug = ?,
                    beschreibung = ?,
                    logik_typ = ?,
                    aktiv = 1,
                    sortierung = ?,
                    aktualisiert_am = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    modell["slug"],
                    modell["beschreibung"],
                    modell["logik_typ"],
                    modell["sortierung"],
                    vorhandenes_modell[0],
                )
            )
        else:
            cursor.execute(
                """
                INSERT INTO lizenz_modelle (
                    name,
                    slug,
                    beschreibung,
                    logik_typ,
                    aktiv,
                    sortierung,
                    erstellt_am,
                    aktualisiert_am
                )
                VALUES (?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    modell["name"],
                    modell["slug"],
                    modell["beschreibung"],
                    modell["logik_typ"],
                    modell["sortierung"],
                )
            )


def standard_zuweisungszieltypen_anlegen(cursor):
    """
    Alte Funktion bleibt aus Kompatibilitätsgründen erhalten.
    Nach neuer Roadmap wird sie aber nicht mehr in datenbank_erstellen() aufgerufen.
    """
    standard_zieltypen = [
        {
            "name": "Benutzer / Account",
            "slug": "benutzer_account",
            "beschreibung": "Lizenz wird einem Benutzerkonto, Account oder einer Person zugeordnet.",
            "basistyp": "benutzer",
            "sortierung": 10,
        },
        {
            "name": "Gerät / Client",
            "slug": "geraet_client",
            "beschreibung": "Lizenz wird einem Gerät, Client, Endpoint oder Arbeitsplatzsystem zugeordnet.",
            "basistyp": "geraet",
            "sortierung": 20,
        },
        {
            "name": "System / Infrastruktur",
            "slug": "system_infrastruktur",
            "beschreibung": "Lizenz wird einem Server, einer Instanz, VM, Datenbank oder Infrastrukturkomponente zugeordnet.",
            "basistyp": "server",
            "sortierung": 30,
        },
        {
            "name": "Organisation / Abteilung",
            "slug": "organisation_abteilung",
            "beschreibung": "Lizenz gilt für eine Organisationseinheit, Abteilung oder Gruppe.",
            "basistyp": "organisation",
            "sortierung": 40,
        },
        {
            "name": "Standort",
            "slug": "standort",
            "beschreibung": "Lizenz gilt für einen Standort oder räumlichen Bereich.",
            "basistyp": "standort",
            "sortierung": 50,
        },
        {
            "name": "Lizenzpool / Vertrag",
            "slug": "lizenzpool_vertrag",
            "beschreibung": "Lizenz wird als Pool, Rahmenvertrag oder gemeinsame Nutzung verwaltet.",
            "basistyp": "pool",
            "sortierung": 60,
        },
        {
            "name": "Dienst / API",
            "slug": "dienst_api",
            "beschreibung": "Lizenz wird einem Dienst, einer API oder einem technischen Service zugeordnet.",
            "basistyp": "service",
            "sortierung": 70,
        },
    ]

    for zieltyp in standard_zieltypen:
        cursor.execute(
            """
            SELECT id
            FROM zuweisungsziel_typen
            WHERE slug = ? OR name = ?
            """,
            (
                zieltyp["slug"],
                zieltyp["name"],
            )
        )

        vorhandener_zieltyp = cursor.fetchone()

        if vorhandener_zieltyp:
            cursor.execute(
                """
                UPDATE zuweisungsziel_typen
                SET
                    slug = ?,
                    beschreibung = ?,
                    basistyp = ?,
                    aktiv = 1,
                    sortierung = ?,
                    aktualisiert_am = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    zieltyp["slug"],
                    zieltyp["beschreibung"],
                    zieltyp["basistyp"],
                    zieltyp["sortierung"],
                    vorhandener_zieltyp[0],
                )
            )
        else:
            cursor.execute(
                """
                INSERT INTO zuweisungsziel_typen (
                    name,
                    slug,
                    beschreibung,
                    basistyp,
                    aktiv,
                    sortierung,
                    erstellt_am,
                    aktualisiert_am
                )
                VALUES (?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    zieltyp["name"],
                    zieltyp["slug"],
                    zieltyp["beschreibung"],
                    zieltyp["basistyp"],
                    zieltyp["sortierung"],
                )
            )


def _datenbank_schema_anlegen(verbindung):
    """Legt das Fachschema innerhalb einer bereits geoeffneten Transaktion an."""
    cursor = verbindung.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS datenquellen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            typ TEXT NOT NULL,
            status TEXT DEFAULT 'nicht_eingerichtet',
            aktiv INTEGER DEFAULT 1,
            letzter_test TEXT,
            letzte_meldung TEXT,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            aktualisiert_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "auth_typ",
        "TEXT"
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "demo_modus",
        "INTEGER DEFAULT 0"
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "konfiguration_info",
        "TEXT"
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "zuweisungen_endpunkt",
        "TEXT"
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "zuweisungen_feld_mapping",
        "TEXT"
    )

    cursor.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'datenquellen'
        """
    )

    datenquellen_definition = cursor.fetchone()

    datenquellen_hat_typ_unique = (
        datenquellen_definition
        and datenquellen_definition[0]
        and "typ TEXT NOT NULL UNIQUE"
        in datenquellen_definition[0]
    )

    if datenquellen_hat_typ_unique:
        cursor.execute(
            """
            CREATE TABLE datenquellen_neu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                typ TEXT NOT NULL,
                status TEXT DEFAULT 'nicht_eingerichtet',
                aktiv INTEGER DEFAULT 1,
                letzter_test TEXT,
                letzte_meldung TEXT,
                erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
                aktualisiert_am TEXT DEFAULT CURRENT_TIMESTAMP,
                auth_typ TEXT,
                demo_modus INTEGER DEFAULT 0,
                konfiguration_info TEXT,
                basis_url TEXT,
                endpunkt TEXT,
                token_url TEXT,
                scope TEXT,
                feld_mapping TEXT,
                auth_daten_verschluesselt TEXT,
                zuweisungen_endpunkt TEXT,
                zuweisungen_feld_mapping TEXT
            )
            """
        )

        cursor.execute(
            """
            INSERT INTO datenquellen_neu (
                id,
                name,
                typ,
                status,
                aktiv,
                letzter_test,
                letzte_meldung,
                erstellt_am,
                aktualisiert_am,
                auth_typ,
                demo_modus,
                konfiguration_info,
                basis_url,
                endpunkt,
                token_url,
                scope,
                feld_mapping,
                auth_daten_verschluesselt,
                zuweisungen_endpunkt,
                zuweisungen_feld_mapping
            )
            SELECT
                id,
                name,
                typ,
                status,
                aktiv,
                letzter_test,
                letzte_meldung,
                erstellt_am,
                aktualisiert_am,
                auth_typ,
                demo_modus,
                konfiguration_info,
                basis_url,
                endpunkt,
                token_url,
                scope,
                feld_mapping,
                auth_daten_verschluesselt,
                zuweisungen_endpunkt,
                zuweisungen_feld_mapping
            FROM datenquellen
            """
        )

        cursor.execute(
            """
            DROP TABLE datenquellen
            """
        )

        cursor.execute(
            """
            ALTER TABLE datenquellen_neu
            RENAME TO datenquellen
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_datenquellen_typ
            ON datenquellen (typ)
            """
        )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_datenquellen_typ
        ON datenquellen (typ)
        """
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "automatische_synchronisation",
        "INTEGER NOT NULL DEFAULT 0"
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "sync_intervall_minuten",
        "INTEGER"
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "datenquellen",
        "naechste_synchronisation",
        "TEXT"
    )

    cursor.execute(
        """
        INSERT INTO datenquellen (
            name,
            typ,
            status,
            aktiv,
            auth_typ,
            demo_modus,
            letzte_meldung,
            erstellt_am,
            aktualisiert_am
        )
        SELECT
            'Active Directory',
            'ad',
            'nicht_eingerichtet',
            1,
            'basic_auth',
            0,
            'Die AD-Datenquelle wurde automatisch eingerichtet.',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1
            FROM datenquellen
            WHERE LOWER(TRIM(typ)) = 'ad'
        )
        """
    )

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'synchronisation_status'
        """
    )

    synchronisation_status_vorhanden = (
        cursor.fetchone() is not None
    )

    synchronisation_status_spalten = set()

    if synchronisation_status_vorhanden:
        cursor.execute(
            """
            PRAGMA table_info(synchronisation_status)
            """
        )

        synchronisation_status_spalten = {
            zeile[1]
            for zeile in cursor.fetchall()
        }

    if (
        synchronisation_status_vorhanden
        and "datenquelle_id"
        not in synchronisation_status_spalten
    ):
        cursor.execute(
            """
            SELECT
                quelle,
                letzte_synchronisation,
                letzter_fehler,
                naechster_erlaubter_abruf,
                status,
                aktualisiert_am
            FROM synchronisation_status
            """
        )

        alte_status_eintraege = [
            {
                "quelle": zeile[0],
                "letzte_synchronisation": zeile[1],
                "letzter_fehler": zeile[2],
                "naechster_erlaubter_abruf": zeile[3],
                "status": zeile[4],
                "aktualisiert_am": zeile[5],
            }
            for zeile in cursor.fetchall()
        ]

        cursor.execute(
            """
            CREATE TABLE synchronisation_status_neu (
                datenquelle_id INTEGER PRIMARY KEY,
                letzte_synchronisation TEXT,
                letzter_fehler TEXT,
                naechster_erlaubter_abruf TEXT,
                status TEXT NOT NULL
                    DEFAULT 'nie_synchronisiert',
                aktualisiert_am TEXT
                    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (datenquelle_id)
                    REFERENCES datenquellen(id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            SELECT
                id,
                name,
                typ
            FROM datenquellen
            """
        )

        datenquellen_fuer_migration = cursor.fetchall()

        for (
            datenquelle_id,
            datenquelle_name,
            datenquelle_typ,
        ) in datenquellen_fuer_migration:
            vergleichswerte = {
                str(datenquelle_name or "")
                .strip()
                .lower(),
                str(datenquelle_typ or "")
                .strip()
                .lower(),
            }

            kandidaten = [
                eintrag
                for eintrag in alte_status_eintraege
                if str(
                    eintrag.get("quelle") or ""
                ).strip().lower()
                in vergleichswerte
            ]

            if not kandidaten:
                continue

            kandidaten.sort(
                key=lambda eintrag: (
                    str(
                        eintrag.get(
                            "aktualisiert_am"
                        )
                        or eintrag.get(
                            "letzte_synchronisation"
                        )
                        or ""
                    ),
                    (
                        str(
                            eintrag.get("quelle")
                            or ""
                        ).strip().lower()
                        == str(
                            datenquelle_typ or ""
                        ).strip().lower()
                    ),
                ),
                reverse=True,
            )

            status_eintrag = kandidaten[0]

            cursor.execute(
                """
                INSERT INTO
                    synchronisation_status_neu (
                        datenquelle_id,
                        letzte_synchronisation,
                        letzter_fehler,
                        naechster_erlaubter_abruf,
                        status,
                        aktualisiert_am
                    )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datenquelle_id,
                    status_eintrag.get(
                        "letzte_synchronisation"
                    ),
                    status_eintrag.get(
                        "letzter_fehler"
                    ),
                    status_eintrag.get(
                        "naechster_erlaubter_abruf"
                    ),
                    status_eintrag.get("status")
                    or "nie_synchronisiert",
                    status_eintrag.get(
                        "aktualisiert_am"
                    ),
                ),
            )

        cursor.execute(
            """
            DROP TABLE synchronisation_status
            """
        )

        cursor.execute(
            """
            ALTER TABLE synchronisation_status_neu
            RENAME TO synchronisation_status
            """
        )

    elif not synchronisation_status_vorhanden:
        cursor.execute(
            """
            CREATE TABLE synchronisation_status (
                datenquelle_id INTEGER PRIMARY KEY,
                letzte_synchronisation TEXT,
                letzter_fehler TEXT,
                naechster_erlaubter_abruf TEXT,
                status TEXT NOT NULL
                    DEFAULT 'nie_synchronisiert',
                aktualisiert_am TEXT
                    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (datenquelle_id)
                    REFERENCES datenquellen(id)
                    ON DELETE CASCADE
            )
            """
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS
            synchronisationslaeufe (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datenquelle_id INTEGER NOT NULL,
                status TEXT NOT NULL
                    DEFAULT 'laeuft',
                gestartet_am TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                beendet_am TEXT,
                angelegt INTEGER NOT NULL DEFAULT 0,
                aktualisiert INTEGER NOT NULL DEFAULT 0,
                deaktiviert INTEGER NOT NULL DEFAULT 0,
                unveraendert INTEGER NOT NULL DEFAULT 0,
                fehlerhaft INTEGER NOT NULL DEFAULT 0,
                meldung TEXT,
                fehlerdetails TEXT,
                ausgeloest_durch TEXT NOT NULL
                    DEFAULT 'manuell',
                FOREIGN KEY (datenquelle_id)
                    REFERENCES datenquellen(id)
                    ON DELETE CASCADE
            )
        """
    )

    vorhandene_sync_spalten = {
        zeile[1]
        for zeile in cursor.execute(
            "PRAGMA table_info(synchronisationslaeufe)"
        ).fetchall()
    }

    if "deaktiviert" not in vorhandene_sync_spalten:
        cursor.execute(
            """
            ALTER TABLE synchronisationslaeufe
            ADD COLUMN deaktiviert INTEGER
                NOT NULL DEFAULT 0
            """
        )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_sync_laeufe_datenquelle
        ON synchronisationslaeufe (
            datenquelle_id,
            gestartet_am
        )
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_sync_laeufe_ein_aktiver_lauf
        ON synchronisationslaeufe (
            datenquelle_id
        )
        WHERE status = 'laeuft'
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lizenz_kategorien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            slug TEXT,
            beschreibung TEXT,
            typische_nutzung TEXT,
            lizenzlogik TEXT,
            typische_zuordnung TEXT,
            interne_lizenzklasse TEXT DEFAULT 'benutzer',
            standard_zuweisungsart TEXT DEFAULT 'benutzer',
            aktiv INTEGER DEFAULT 1,
            archiviert INTEGER DEFAULT 0,
            archiviert_am TEXT,
            archivierungsgrund TEXT,
            sortierung INTEGER DEFAULT 100,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            aktualisiert_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lizenz_modelle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE,
            beschreibung TEXT,
            logik_typ TEXT NOT NULL,
            aktiv INTEGER DEFAULT 1,
            sortierung INTEGER DEFAULT 100,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            aktualisiert_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zuweisungsziel_typen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE,
            beschreibung TEXT,
            basistyp TEXT NOT NULL,
            aktiv INTEGER DEFAULT 1,
            sortierung INTEGER DEFAULT 100,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            aktualisiert_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anbieter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            beschreibung TEXT,
            webseite TEXT,
            aktiv INTEGER DEFAULT 1,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            aktualisiert_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "slug", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "beschreibung", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "typische_nutzung", "TEXT")

    # Alte Kategorie-Felder bleiben für Kompatibilität bestehen,
    # werden nach neuer Roadmap aber nicht mehr aktiv in der UI genutzt.
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "lizenzlogik", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "typische_zuordnung", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "interne_lizenzklasse", "TEXT DEFAULT 'benutzer'")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "standard_zuweisungsart", "TEXT DEFAULT 'benutzer'")

    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "aktiv", "INTEGER DEFAULT 1")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "archiviert", "INTEGER DEFAULT 0")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "archiviert_am", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "archivierungsgrund", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "sortierung", "INTEGER DEFAULT 100")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "erstellt_am", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_kategorien", "aktualisiert_am", "TEXT")

    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "name", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "slug", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "beschreibung", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "logik_typ", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "aktiv", "INTEGER DEFAULT 1")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "sortierung", "INTEGER DEFAULT 100")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "erstellt_am", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_modelle", "aktualisiert_am", "TEXT")

    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "name", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "slug", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "beschreibung", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "basistyp", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "aktiv", "INTEGER DEFAULT 1")
    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "sortierung", "INTEGER DEFAULT 100")
    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "erstellt_am", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "zuweisungsziel_typen", "aktualisiert_am", "TEXT")

    spalte_hinzufuegen_wenn_fehlt(cursor, "anbieter", "name", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "anbieter", "beschreibung", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "anbieter", "webseite", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "anbieter", "aktiv", "INTEGER DEFAULT 1")
    spalte_hinzufuegen_wenn_fehlt(cursor, "anbieter", "erstellt_am", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "anbieter", "aktualisiert_am", "TEXT")

    cursor.execute("""
        UPDATE lizenz_kategorien
        SET erstellt_am = CURRENT_TIMESTAMP
        WHERE erstellt_am IS NULL OR erstellt_am = ''
    """)

    cursor.execute("""
        UPDATE lizenz_kategorien
        SET aktualisiert_am = CURRENT_TIMESTAMP
        WHERE aktualisiert_am IS NULL OR aktualisiert_am = ''
    """)

    cursor.execute("""
        UPDATE lizenz_modelle
        SET erstellt_am = CURRENT_TIMESTAMP
        WHERE erstellt_am IS NULL OR erstellt_am = ''
    """)

    cursor.execute("""
        UPDATE lizenz_modelle
        SET aktualisiert_am = CURRENT_TIMESTAMP
        WHERE aktualisiert_am IS NULL OR aktualisiert_am = ''
    """)

    cursor.execute("""
        UPDATE zuweisungsziel_typen
        SET erstellt_am = CURRENT_TIMESTAMP
        WHERE erstellt_am IS NULL OR erstellt_am = ''
    """)

    cursor.execute("""
        UPDATE zuweisungsziel_typen
        SET aktualisiert_am = CURRENT_TIMESTAMP
        WHERE aktualisiert_am IS NULL OR aktualisiert_am = ''
    """)

    cursor.execute("""
        UPDATE anbieter
        SET erstellt_am = CURRENT_TIMESTAMP
        WHERE erstellt_am IS NULL OR erstellt_am = ''
    """)

    cursor.execute("""
        UPDATE anbieter
        SET aktualisiert_am = CURRENT_TIMESTAMP
        WHERE aktualisiert_am IS NULL OR aktualisiert_am = ''
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lizenzen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            anbieter TEXT NOT NULL,
            anzahl INTEGER NOT NULL,
            lizenztyp TEXT,
            kosten REAL,
            ablaufdatum TEXT,
            verlaengerungsdatum TEXT
        )
    """)

    # Alte Felder bleiben zunächst bestehen, werden aber nicht mehr
    # im Fokus der neuen UI genutzt.
    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "lizenzklasse",
        "TEXT DEFAULT 'benutzer'",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "zuweisungsart",
        "TEXT DEFAULT 'benutzer'",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "kostenmodell",
        "TEXT DEFAULT 'fortlaufend'",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "technologiebereich",
        "TEXT DEFAULT 'allgemein'",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "kategorie_id",
        "INTEGER",
    )

    # Alte Modell-/Zieltyp-Spalten bleiben aus
    # Kompatibilitätsgründen bestehen.
    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "lizenzmodell_id",
        "INTEGER",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "zuweisungszieltyp_id",
        "INTEGER",
    )

    # Neue Felder für die vereinfachte Roadmap.
    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "beschreibung",
        "TEXT",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "datenquelle",
        "TEXT DEFAULT 'manuell'",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "datenquelle_id",
        "INTEGER",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "api_sync_aktiv",
        "INTEGER DEFAULT 0",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "externe_id",
        "TEXT",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "status",
        "TEXT DEFAULT 'aktiv'",
    )

    # Von einer externen Quelle gemeldete Vertrags- und Nutzungswerte.
    # Sie bleiben getrennt von den lokal nachvollziehbaren Zuweisungen.
    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "externer_verbrauch",
        "INTEGER",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "verbrauch_gemeldet_am",
        "TEXT",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "startdatum",
        "TEXT",
    )

    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "lizenzen",
        "externer_produktschluessel",
        "TEXT",
    )

    # Schneller Zugriff auf alle Lizenzen einer Datenquelle.
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_lizenzen_datenquelle_id
        ON lizenzen (
            datenquelle_id
        )
        """
    )

    # Eine externe ID darf innerhalb derselben Datenquelle
    # nur einmal vorkommen.
    #
    # Leere externe IDs und manuelle Lizenzen bleiben erlaubt.
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_lizenzen_quelle_externe_id
        ON lizenzen (
            datenquelle_id,
            externe_id
        )
        WHERE datenquelle_id IS NOT NULL
          AND TRIM(COALESCE(externe_id, '')) != ''
        """
    )

    # Nur Lizenzen migrieren, die ausdrücklich aus Adobe stammen.
    cursor.execute(
        """
        UPDATE lizenzen
        SET datenquelle_id = (
            SELECT id
            FROM datenquellen
            WHERE typ = 'adobe'
            ORDER BY id
            LIMIT 1
        )
        WHERE datenquelle_id IS NULL
          AND LOWER(
              TRIM(
                  COALESCE(
                      datenquelle,
                      ''
                  )
              )
          ) = 'adobe'
          AND EXISTS (
              SELECT 1
              FROM datenquellen
              WHERE typ = 'adobe'
          )
        """
    )

    # Alte Werte wie rest_api:8 auf datenquelle_id = 8 migrieren.
    cursor.execute(
        """
        UPDATE lizenzen
        SET datenquelle_id = CAST(
            SUBSTR(
                datenquelle,
                10
            )
            AS INTEGER
        )
        WHERE datenquelle_id IS NULL
          AND datenquelle GLOB 'rest_api:[0-9]*'
          AND EXISTS (
              SELECT 1
              FROM datenquellen
              WHERE id = CAST(
                  SUBSTR(
                      lizenzen.datenquelle,
                      10
                  )
                  AS INTEGER
              )
          )
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS benutzer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            benutzername TEXT NOT NULL UNIQUE,
            email TEXT,
            abteilung TEXT,
            aktiv INTEGER DEFAULT 1
        )
    """)

    spalte_hinzufuegen_wenn_fehlt(cursor, "benutzer", "vorname", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "benutzer", "nachname", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "benutzer", "quelle", "TEXT DEFAULT 'manuell'")
    spalte_hinzufuegen_wenn_fehlt(cursor, "benutzer", "externe_id", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "benutzer", "zuletzt_synchronisiert", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(
        cursor,
        "benutzer",
        "deaktivierungsgrund",
        "TEXT",
    )

    # Bei externen Hinweisdatensaetzen ist bereits eindeutig bekannt, dass
    # beim Abgleich kein lokales AD-Konto gefunden wurde. Fuer manuell
    # deaktivierte Konten wird ebenfalls ein neutraler Ausgangswert ergaenzt.
    cursor.execute(
        """
        UPDATE benutzer
        SET deaktivierungsgrund = ?
        WHERE aktiv = 0
          AND TRIM(COALESCE(deaktivierungsgrund, '')) = ''
          AND LOWER(TRIM(COALESCE(quelle, ''))) LIKE 'rest_api:%'
        """,
        (NICHT_IM_AD_GEFUNDEN,),
    )
    cursor.execute(
        """
        UPDATE benutzer
        SET deaktivierungsgrund = ?
        WHERE aktiv = 0
          AND TRIM(COALESCE(deaktivierungsgrund, '')) = ''
          AND LOWER(TRIM(COALESCE(quelle, ''))) IN ('web', 'manuell')
        """,
        (MANUELL_DEAKTIVIERT,),
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zuweisungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            benutzer_id INTEGER NOT NULL,
            lizenz_id INTEGER NOT NULL,
            zuweisungsdatum TEXT NOT NULL,
            status TEXT DEFAULT 'aktiv',
            FOREIGN KEY (benutzer_id) REFERENCES benutzer(id),
            FOREIGN KEY (lizenz_id) REFERENCES lizenzen(id),
            UNIQUE (benutzer_id, lizenz_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS geraete (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            inventarnummer TEXT,
            seriennummer TEXT,
            geraetetyp TEXT,
            status TEXT DEFAULT 'aktiv'
        )
    """)

    # Externe Geräte/Endpoints werden quellenbezogen erkannt. Manuell
    # gepflegte Geräte bleiben davon unberührt.
    # Historische Erstellungsdaten sind unbekannt und bleiben NULL.
    spalte_hinzufuegen_wenn_fehlt(
        cursor, "geraete", "erstellt_am", "TEXT"
    )
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS geraete_erstellungsdatum
        AFTER INSERT ON geraete
        WHEN NEW.erstellt_am IS NULL
        BEGIN
            UPDATE geraete SET erstellt_am = DATETIME('now') WHERE id = NEW.id;
        END
    """)
    spalte_hinzufuegen_wenn_fehlt(
        cursor, "geraete", "quelle", "TEXT DEFAULT 'manuell'"
    )
    spalte_hinzufuegen_wenn_fehlt(
        cursor, "geraete", "datenquelle_id", "INTEGER"
    )
    spalte_hinzufuegen_wenn_fehlt(
        cursor, "geraete", "externe_id", "TEXT"
    )
    spalte_hinzufuegen_wenn_fehlt(
        cursor, "geraete", "zuletzt_synchronisiert", "TEXT"
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_geraete_quelle_externe_id
        ON geraete (datenquelle_id, externe_id)
        WHERE datenquelle_id IS NOT NULL
          AND TRIM(COALESCE(externe_id, '')) != ''
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hostname TEXT,
            ip_adresse TEXT,
            betriebssystem TEXT,
            status TEXT DEFAULT 'aktiv'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lizenz_zuweisungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lizenz_id INTEGER NOT NULL,
            ziel_typ TEXT NOT NULL,
            ziel_id INTEGER NOT NULL,
            zuweisungsdatum TEXT,
            status TEXT DEFAULT 'aktiv'
        )
    """)

    # Neue Sync-/Quellenfelder für automatische API-Zuweisungen.
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_zuweisungen", "quelle", "TEXT DEFAULT 'manuell'")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_zuweisungen", "externe_id", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_zuweisungen", "synchronisiert_am", "TEXT")
    spalte_hinzufuegen_wenn_fehlt(cursor, "lizenz_zuweisungen", "entfernt_am", "TEXT")

    # Stammdaten anlegen/aktualisieren.
    standard_lizenzkategorien_anlegen(cursor)
    standard_anbieter_anlegen(cursor)

    # Alte Standarddaten werden nicht mehr aktiv angelegt.
    # Die Tabellen bleiben nur aus Kompatibilitätsgründen bestehen.
    # standard_lizenzmodelle_anlegen(cursor)
    # standard_zuweisungszieltypen_anlegen(cursor)

def datenbank_erstellen():
    """Initialisiert oder ergaenzt die Fachdatenbank transaktional.

    Die Funktion kann auf einer neuen wie auf einer bereits vorhandenen
    Datenbank erneut ausgefuehrt werden. Im Fehlerfall wird die laufende
    Transaktion verworfen und die Verbindung in jedem Fall geschlossen.
    """
    verbindung = verbindung_oeffnen()

    try:
        _datenbank_schema_anlegen(verbindung)
        verbindung.commit()
    except Exception:
        verbindung.rollback()
        raise
    finally:
        verbindung.close()
