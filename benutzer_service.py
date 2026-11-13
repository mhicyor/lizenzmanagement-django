import os
import re

from benutzer_status_service import MANUELL_DEAKTIVIERT
from database import verbindung_oeffnen


TECHNISCHE_BENUTZER_MARKER = (
    "akn",
    "anw",
    "adminkonto",
    "application",
    "autoklave",
    "azure",
    "backup",
    "bckup",
    "bioread",
    "bosch",
    "betriebsrat",
    "bibliothek",
    "cnl",
    "concect",
    "concheded",
    "conject",
    "contract",
    "coronatest",
    "courses",
    "dienststarter",
    "domjoin",
    "documents",
    "dropbox",
    "easyvet",
    "einkauf",
    "exchange",
    "extest",
    "fb",
    "filemaker",
    "fluo",
    "fotopreis",
    "gast",
    "gelddoku",
    "genetik",
    "glt",
    "gtpn",
    "healthmailbox",
    "idsoft",
    "infmod",
    "inventor",
    "kamera",
    "kiosk",
    "labor",
    "ldap",
    "mailbox",
    "matlab",
    "mikroskop",
    "mlabchart",
    "mustermann",
    "musterfrau",
    "nanodrop",
    "nextcloud",
    "noreply",
    "novatime",
    "officemaster",
    "osticket",
    "pacs",
    "phylogenie",
    "plabchart",
    "posterdrucker",
    "prakti",
    "printer",
    "repro",
    "scanner",
    "sccm",
    "scom",
    "scsm",
    "scil",
    "scpg",
    "sekretariat",
    "service",
    "setup",
    "snl",
    "sopdoc",
    "sequenzen",
    "sorter",
    "sql",
    "sync",
    "telemetrie",
    "voip",
    "vosb",
    "vpn",
    "vt",
)

TECHNISCHE_BENUTZER_PHRASEN = (
    "ancient dna lab",
    "bosch kamera",
    "bundes rechnungshof",
    "deutsches primatenzentrum",
    "dropbox business admin",
    "einkauf dpz",
    "exchange administrator",
    "file maker",
    "fluo.mikroskop",
    "kiosk mode",
    "maclean-erkelenz stiftung",
    "mittelverwaltung dfg",
    "neural networking",
    "office master",
    "primate neurobiology",
    "sosafe training",
    "telemetrie einheit",
)

TECHNISCHE_BENUTZER_ROLLEN_MARKER = (
    "admin",
    "administrator",
    "adminkonto",
    "betrieb",
    "betriebstechnik",
    "controller",
    "einkauf",
    "elektro",
    "gast",
    "guest",
    "labor",
    "lab",
    "mail",
    "migration",
    "report",
    "sekretariat",
    "server",
    "storage",
    "support",
    "svc",
    "task",
    "technik",
    "ticket",
    "training",
)


def _technische_benutzer_marker():
    konfiguration = os.getenv("BENUTZER_TECHNISCHE_KONTO_MARKER")

    if not konfiguration or not konfiguration.strip():
        return TECHNISCHE_BENUTZER_MARKER

    return tuple(
        eintrag.strip().lower()
        for eintrag in konfiguration.split(",")
        if eintrag.strip()
    )


def _technische_benutzer_phrasen():
    konfiguration = os.getenv("BENUTZER_TECHNISCHE_KONTO_PHRASEN")

    if not konfiguration or not konfiguration.strip():
        return TECHNISCHE_BENUTZER_PHRASEN

    return tuple(
        eintrag.strip().lower()
        for eintrag in konfiguration.split(",")
        if eintrag.strip()
    )


def _technische_benutzer_rollen_marker():
    konfiguration = os.getenv("BENUTZER_TECHNISCHE_KONTO_ROLLEN_MARKER")

    if not konfiguration or not konfiguration.strip():
        return TECHNISCHE_BENUTZER_ROLLEN_MARKER

    return tuple(
        eintrag.strip().lower()
        for eintrag in konfiguration.split(",")
        if eintrag.strip()
    )


def _tokens(text):
    return {
        token
        for token in re.split(r"[^a-z0-9äöüß]+", str(text or "").lower())
        if token
    }


def _kompakter_text(text):
    return re.sub(
        r"[^a-z0-9äöüß]+",
        "",
        str(text or "").lower(),
    )


def _ist_personenname(name):
    name_text = str(name or "").strip()

    if not name_text:
        return False

    name_tokens = [
        token
        for token in re.split(r"[\s,._-]+", name_text)
        if re.search(r"[A-Za-zÄÖÜäöüß]", token or "")
    ]

    if len(name_tokens) < 2:
        return False

    gross_geschriebene_tokens = [
        token
        for token in name_tokens
        if token[:1].isupper()
    ]

    return len(gross_geschriebene_tokens) >= 2


def ist_technisches_benutzerkonto(name, benutzername="", email=""):
    """
    Erkennt lokale Funktions-, Test- und Sammelkonten für die Benutzeransicht.

    Die Regel ist bewusst vorsichtig: Normale Personen mit einer dpz.eu-Mail
    bleiben sichtbar. Ausgeblendet werden typische Konto-Namen wie "AKN:",
    "DPZ:", "Conject", "Kiosk", "Setup" oder Backup-/Service-Konten.
    """
    name_text = str(name or "").strip()
    benutzername_text = str(benutzername or "").strip()
    email_text = str(email or "").strip()

    if not name_text:
        return True

    konto_text = f"{name_text} {benutzername_text}".lower()
    kompakter_konto_text = _kompakter_text(konto_text)
    personenname = _ist_personenname(name_text)

    if ":" in name_text:
        return True

    for phrase in _technische_benutzer_phrasen():
        if phrase in konto_text:
            return True

    marker = set(_technische_benutzer_marker())
    rollen_marker = set(_technische_benutzer_rollen_marker())
    konto_tokens = _tokens(konto_text)
    email_lokalteil = email_text.split("@", 1)[0]
    email_tokens = _tokens(email_lokalteil)
    kompakter_email_lokalteil = _kompakter_text(email_lokalteil)

    if konto_tokens.intersection(marker):
        return True

    if email_tokens.intersection(marker.difference({"dpz"})):
        return True

    if any(
        markierung
        and len(markierung) >= 5
        and markierung in kompakter_konto_text
        for markierung in marker
    ):
        return True

    if kompakter_email_lokalteil and any(
        markierung
        and len(markierung) >= 5
        and markierung in kompakter_email_lokalteil
        for markierung in marker.difference({"dpz"})
    ):
        return True

    if not personenname:
        if konto_tokens.intersection(rollen_marker):
            return True

        if any(
            markierung
            and markierung in kompakter_konto_text
            for markierung in rollen_marker
        ):
            return True

    if any(
        token.startswith("test")
        and any(zeichen.isdigit() for zeichen in token)
        for token in konto_tokens
    ):
        return True

    name_tokens = _tokens(name_text)
    if name_tokens and all(len(token) <= 1 for token in name_tokens):
        return True

    kompakter_name = _kompakter_text(name_text)
    kompakter_benutzername = _kompakter_text(benutzername_text)

    if (
        kompakter_name
        and kompakter_benutzername
        and kompakter_name == kompakter_benutzername
        and not personenname
    ):
        return True

    if not email_text and not personenname:
        return True

    if (
        name_text.lower() == name_text
        and not personenname
    ):
        return True

    return False


def filtere_reale_benutzerkonten(benutzer):
    """Entfernt technische Konten aus Listen für UI und Export."""
    return [
        eintrag
        for eintrag in benutzer
        if not ist_technisches_benutzerkonto(
            eintrag[1] if len(eintrag) > 1 else "",
            eintrag[2] if len(eintrag) > 2 else "",
            eintrag[3] if len(eintrag) > 3 else "",
        )
    ]


def lade_benutzer_uebersicht(abteilung_filter=None, status_filter="aktiv"):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    bedingungen = []
    parameter = []

    if status_filter == "aktiv":
        bedingungen.append("aktiv = 1")
    elif status_filter == "deaktiviert":
        bedingungen.append("aktiv = 0")

    if abteilung_filter and abteilung_filter != "Alle Abteilungen":
        bedingungen.append("abteilung = TRIM(?)")
        parameter.append(abteilung_filter)

    where_clause = (
        "WHERE " + " AND ".join(bedingungen)
        if bedingungen
        else ""
    )

    cursor.execute(
        f"""
        SELECT id, name, benutzername, email, abteilung, aktiv
        FROM benutzer
        {where_clause}
        ORDER BY name
        """,
        parameter,
    )

    daten = cursor.fetchall()
    verbindung.close()

    formatierte_daten = []

    for benutzer in daten:
        status = "aktiv" if benutzer[5] == 1 else "deaktiviert"

        formatierte_daten.append(
            (
                benutzer[0],
                benutzer[1],
                benutzer[2],
                benutzer[3],
                benutzer[4],
                status
            )
        )

    return formatierte_daten


def lade_benutzer_exportdaten(benutzer_ids):
    """Lädt Benutzer samt aktiven personenbezogenen Lizenznamen."""
    ids = []
    for benutzer_id in benutzer_ids or []:
        try:
            ids.append(int(benutzer_id))
        except (TypeError, ValueError):
            continue

    if not ids:
        return []

    platzhalter = ", ".join("?" for _ in ids)
    verbindung = verbindung_oeffnen()

    try:
        zeilen = verbindung.execute(
            f"""
            SELECT
                b.id,
                b.name,
                b.vorname,
                b.nachname,
                b.benutzername,
                b.email,
                b.abteilung,
                b.aktiv,
                l.name AS lizenzname
            FROM benutzer AS b
            LEFT JOIN zuweisungen AS z
                ON z.benutzer_id = b.id
               AND z.status = 'aktiv'
            LEFT JOIN lizenzen AS l
                ON l.id = z.lizenz_id
               AND COALESCE(
                    NULLIF(TRIM(l.zuweisungsart), ''),
                    NULLIF(TRIM(l.lizenzklasse), ''),
                    'benutzer'
               ) = 'benutzer'
            WHERE b.id IN ({platzhalter})
            ORDER BY b.name, l.name
            """,
            ids,
        ).fetchall()
    finally:
        verbindung.close()

    benutzer_nach_id = {}

    for zeile in zeilen:
        benutzer_id = int(zeile[0])
        eintrag = benutzer_nach_id.setdefault(
            benutzer_id,
            {
                "id": benutzer_id,
                "name": str(zeile[1] or "").strip(),
                "vorname": str(zeile[2] or "").strip(),
                "nachname": str(zeile[3] or "").strip(),
                "benutzername": str(zeile[4] or "").strip(),
                "email": str(zeile[5] or "").strip(),
                "abteilung": str(zeile[6] or "").strip(),
                "status": (
                    "aktiv"
                    if int(zeile[7] or 0) == 1
                    else "deaktiviert"
                ),
                "lizenzen": [],
            },
        )

        lizenzname = str(zeile[8] or "").strip()
        if lizenzname and lizenzname not in eintrag["lizenzen"]:
            eintrag["lizenzen"].append(lizenzname)

    return list(benutzer_nach_id.values())


def lade_abteilungen():
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT DISTINCT abteilung
        FROM benutzer
        WHERE abteilung IS NOT NULL
          AND abteilung != ''
          AND aktiv = 1
        ORDER BY abteilung
    """)

    daten = cursor.fetchall()
    verbindung.close()

    abteilungen = ["Alle Abteilungen"]

    for eintrag in daten:
        abteilungen.append(eintrag[0])

    return abteilungen


def lade_aktive_benutzer_ids_fuer_lizenz(
    lizenz_id,
):
    verbindung = verbindung_oeffnen()

    try:
        zeilen = verbindung.execute(
            """
            SELECT DISTINCT benutzer_id
            FROM zuweisungen AS z
            JOIN lizenzen AS l
              ON l.id = z.lizenz_id
            WHERE z.lizenz_id = ?
              AND z.status = 'aktiv'
              AND COALESCE(
                    NULLIF(TRIM(l.zuweisungsart), ''),
                    NULLIF(TRIM(l.lizenzklasse), ''),
                    'benutzer'
              ) = 'benutzer'
            """,
            (lizenz_id,),
        ).fetchall()
    finally:
        verbindung.close()

    return {
        int(zeile[0])
        for zeile in zeilen
    }


def lade_aktive_benutzer_ids_mit_lizenz(status_filter="aktiv"):
    """Lädt Benutzer mit mindestens einer aktiven personenbezogenen Lizenz."""
    verbindung = verbindung_oeffnen()

    status_bedingung = ""
    if status_filter == "aktiv":
        status_bedingung = "AND b.aktiv = 1"
    elif status_filter == "deaktiviert":
        status_bedingung = "AND b.aktiv = 0"

    try:
        zeilen = verbindung.execute(
            f"""
            SELECT DISTINCT z.benutzer_id
            FROM zuweisungen AS z
            JOIN benutzer AS b
              ON b.id = z.benutzer_id
            JOIN lizenzen AS l
              ON l.id = z.lizenz_id
            WHERE z.status = 'aktiv'
              AND COALESCE(
                    NULLIF(TRIM(l.zuweisungsart), ''),
                    NULLIF(TRIM(l.lizenzklasse), ''),
                    'benutzer'
              ) = 'benutzer'
              {status_bedingung}
            """
        ).fetchall()
    finally:
        verbindung.close()

    return {
        int(zeile[0])
        for zeile in zeilen
    }


def loesche_benutzer_mit_zuweisungen(benutzer_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        DELETE FROM zuweisungen
        WHERE benutzer_id = ?
    """, (benutzer_id,))

    cursor.execute("""
        DELETE FROM benutzer
        WHERE id = ?
    """, (benutzer_id,))

    geloescht = cursor.rowcount

    verbindung.commit()
    verbindung.close()

    return geloescht


def deaktiviere_benutzer(benutzer_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        UPDATE benutzer
        SET
            aktiv = 0,
            deaktivierungsgrund = ?
        WHERE id = ?
    """, (MANUELL_DEAKTIVIERT, benutzer_id))

    geaendert = cursor.rowcount

    verbindung.commit()
    verbindung.close()

    return geaendert


def aktiviere_benutzer(benutzer_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        UPDATE benutzer
        SET
            aktiv = 1,
            deaktivierungsgrund = NULL
        WHERE id = ?
    """, (benutzer_id,))

    geaendert = cursor.rowcount

    verbindung.commit()
    verbindung.close()

    return geaendert


def benutzer_hinzufuegen(name, benutzername, email, abteilung):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        INSERT INTO benutzer
            (name, benutzername, email, abteilung, aktiv, quelle)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        name,
        benutzername,
        email,
        abteilung,
        1,
        "Web"
    ))

    verbindung.commit()
    verbindung.close()


def lade_benutzer_details(benutzer_id):
    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    cursor.execute("""
        SELECT id, name, benutzername, email, abteilung, aktiv, quelle
        FROM benutzer
        WHERE id = ?
    """, (benutzer_id,))

    benutzer = cursor.fetchone()

    cursor.execute("""
        SELECT
            l.name,
            l.anbieter,
            l.lizenztyp,
            l.kosten,
            z.zuweisungsdatum,
            z.status,
            l.id
        FROM zuweisungen z
        JOIN lizenzen l ON z.lizenz_id = l.id
        WHERE z.benutzer_id = ?
          AND z.status = 'aktiv'
        ORDER BY l.name
    """, (benutzer_id,))

    aktive_lizenzen = cursor.fetchall()

    cursor.execute("""
        SELECT
            l.name,
            l.anbieter,
            l.lizenztyp,
            l.kosten,
            z.zuweisungsdatum,
            z.status,
            l.id
        FROM zuweisungen z
        JOIN lizenzen l ON z.lizenz_id = l.id
        WHERE z.benutzer_id = ?
          AND z.status != 'aktiv'
        ORDER BY z.zuweisungsdatum DESC, l.name
    """, (benutzer_id,))

    entfernte_lizenzen = cursor.fetchall()

    verbindung.close()

    return benutzer, aktive_lizenzen, entfernte_lizenzen
