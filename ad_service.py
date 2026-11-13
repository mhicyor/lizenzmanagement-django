import os

from dotenv import load_dotenv
from ldap3 import Server, Connection, ALL

from benutzer_status_service import (
    AD_KONTO_DEAKTIVIERT,
    NICHT_IM_AD_GEFUNDEN,
    TECHNISCHES_KONTO,
)
from database import verbindung_oeffnen

from sync_status_service import (
    SynchronisationLaeuftBereits,
    erfolgreiche_synchronisation_speichern,
    fehler_speichern,
    synchronisationslauf_erfolgreich_beenden,
    synchronisationslauf_fehlerhaft_beenden,
    synchronisationslauf_starten,
)

load_dotenv()


STANDARD_TECHNISCHE_KONTO_MUSTER = (
    "admin",
    "betriebsrat",
    "ldap",
    "ipam",
    "svc",
    "service",
    "setup",
    "scanner",
    "drucker",
    "printer",
    "test",
    "mustermann",
    "protocol",
    "rechnungshof",
    "sekretariat",
    "einkauf",
    "conject",
    "ethology",
    "networking",
    "scil",
    "scll",
    "xbi",
)

STANDARD_TECHNISCHE_EMAIL_MUSTER = (
    "admin",
    "ldap",
    "ipam",
    "svc",
    "service",
    "scanner",
    "drucker",
    "printer",
)


def _muster_aus_umgebung(name, standard):
    konfigurierter_wert = os.getenv(name)

    if not konfigurierter_wert or not konfigurierter_wert.strip():
        return standard

    return tuple(
        muster.strip().lower()
        for muster in konfigurierter_wert.split(",")
        if muster.strip()
    )


def lade_ad_konfiguration():
    return {
        "server": os.getenv("AD_SERVER"),
        "port": os.getenv("AD_PORT", "389"),
        "user": os.getenv("AD_USER"),
        "password": os.getenv("AD_PASSWORD"),
        "base_dn": os.getenv("AD_BASE_DN"),
    }


def ad_konfiguration_vollstaendig():
    konfiguration = lade_ad_konfiguration()

    fehlende_felder = [
        feld for feld, wert in konfiguration.items()
        if not wert or str(wert).strip() == ""
    ]

    return len(fehlende_felder) == 0, fehlende_felder


def ad_verbindung_testen():
    vollstaendig, fehlende_felder = ad_konfiguration_vollstaendig()

    if not vollstaendig:
        return False, f"AD-Konfiguration unvollständig: {', '.join(fehlende_felder)}"

    konfiguration = lade_ad_konfiguration()

    try:
        server = Server(
            konfiguration["server"],
            port=int(konfiguration["port"]),
            get_info=ALL
        )

        verbindung = Connection(
            server,
            user=konfiguration["user"],
            password=konfiguration["password"],
            auto_bind=True
        )

        verbindung.unbind()

        return True, "AD-Verbindung erfolgreich."

    except Exception as fehler:
        return False, f"AD-Verbindung fehlgeschlagen: {fehler}"


def ist_technisches_ad_konto(name, vorname, nachname, benutzername, email, distinguished_name):
    name_text = " ".join([
        name or "",
        vorname or "",
        nachname or "",
        benutzername or "",
        distinguished_name or "",
    ]).lower()

    email_text = (email or "").lower()

    muster_name_oder_benutzername = _muster_aus_umgebung(
        "AD_TECHNISCHE_KONTO_MUSTER",
        STANDARD_TECHNISCHE_KONTO_MUSTER,
    )
    muster_email = _muster_aus_umgebung(
        "AD_TECHNISCHE_EMAIL_MUSTER",
        STANDARD_TECHNISCHE_EMAIL_MUSTER,
    )

    for muster in muster_name_oder_benutzername:
        if muster in name_text:
            return True

    for muster in muster_email:
        if muster in email_text:
            return True

    return False


def ad_konto_ist_deaktiviert(user_account_control):
    """Prueft das Deaktivierungsbit eines AD-Benutzerkontos."""
    try:
        wert = int(str(user_account_control or "0").strip())
    except (TypeError, ValueError):
        return False

    return bool(wert & 2)


def _deaktiviere_technische_lokale_ad_konten(cursor):
    """
    Entfernt technische oder testartige AD-Konten aus der aktiven Benutzerliste.

    Der AD-Abruf kann solche Konten zwar fachlich überspringen, ältere lokale
    Datensätze bleiben aber sonst aktiv, wenn das Konto im AD noch existiert.
    Deshalb wird nach dem eigentlichen Sync noch einmal lokal bereinigt.
    Lizenzzuweisungen werden dabei nicht gelöscht.
    """
    lokale_konten = cursor.execute(
        """
        SELECT
            id,
            name,
            vorname,
            nachname,
            benutzername,
            email
        FROM benutzer
        WHERE quelle = 'AD'
          AND aktiv = 1
        """
    ).fetchall()

    deaktiviert = 0

    for konto in lokale_konten:
        if ist_technisches_ad_konto(
            name=konto[1],
            vorname=konto[2],
            nachname=konto[3],
            benutzername=konto[4],
            email=konto[5],
            distinguished_name="",
        ):
            cursor.execute(
                """
                UPDATE benutzer
                SET
                    aktiv = 0,
                    deaktivierungsgrund = ?
                WHERE id = ?
                """,
                (TECHNISCHES_KONTO, konto[0]),
            )
            deaktiviert += cursor.rowcount

    return deaktiviert


def ad_benutzer_laden():
    vollstaendig, fehlende_felder = ad_konfiguration_vollstaendig()

    if not vollstaendig:
        return (
            False,
            (
                "AD-Konfiguration unvollständig: "
                f"{', '.join(fehlende_felder)}"
            ),
            [],
            [],
        )

    konfiguration = lade_ad_konfiguration()

    try:
        server = Server(
            konfiguration["server"],
            port=int(konfiguration["port"]),
            get_info=ALL
        )

        verbindung = Connection(
            server,
            user=konfiguration["user"],
            password=konfiguration["password"],
            auto_bind=True
        )

        suchfilter = (
            "(&"
            "(objectClass=user)"
            "(objectCategory=person)"
            ")"
        )

        attribute = [
            "cn",
            "givenName",
            "sn",
            "mail",
            "sAMAccountName",
            "userPrincipalName",
            "department",
            "employeeID",
            "employeeNumber",
            "objectGUID",
            "distinguishedName",
            "userAccountControl",
        ]

        verbindung.search(
            search_base=konfiguration["base_dn"],
            search_filter=suchfilter,
            attributes=attribute
        )

        benutzer_liste = []
        vorhandene_ad_konten = []
        gesehene_schluessel = set()
        uebersprungene_technische_konten = 0
        deaktivierte_ad_konten = 0
        uebersprungene_duplikate = 0

        for eintrag in verbindung.entries:
            def wert(attr):
                if attr in eintrag and eintrag[attr].value is not None:
                    return str(eintrag[attr].value).strip()
                return ""

            vorname = wert("givenName")
            nachname = wert("sn")
            email = wert("mail")
            sam_account = wert("sAMAccountName")
            upn = wert("userPrincipalName")
            abteilung = wert("department")
            distinguished_name = wert("distinguishedName")
            konto_deaktiviert = ad_konto_ist_deaktiviert(
                wert("userAccountControl")
            )

            externe_id = (
                wert("employeeID")
                or wert("employeeNumber")
                or wert("objectGUID")
            )

            benutzername = sam_account or upn

            if (
                email
                or benutzername
                or externe_id
            ):
                vorhandene_ad_konten.append({
                    "email": email,
                    "benutzername": benutzername,
                    "externe_id": externe_id,
                    "deaktiviert": konto_deaktiviert,
                })

            if konto_deaktiviert:
                deaktivierte_ad_konten += 1
                continue

            if sam_account.endswith("$"):
                uebersprungene_technische_konten += 1
                continue

            if not vorname or not nachname:
                uebersprungene_technische_konten += 1
                continue

            if not email and not sam_account and not upn and not externe_id:
                uebersprungene_technische_konten += 1
                continue

            name = f"{vorname} {nachname}".strip()

            if ist_technisches_ad_konto(
                name=name,
                vorname=vorname,
                nachname=nachname,
                benutzername=benutzername,
                email=email,
                distinguished_name=distinguished_name,
            ):
                uebersprungene_technische_konten += 1
                continue

            eindeutiger_schluessel = (
                email.lower()
                or upn.lower()
                or sam_account.lower()
                or externe_id.lower()
            )

            if eindeutiger_schluessel in gesehene_schluessel:
                uebersprungene_duplikate += 1
                continue

            gesehene_schluessel.add(eindeutiger_schluessel)

            benutzer_liste.append({
                "name": name,
                "vorname": vorname,
                "nachname": nachname,
                "email": email,
                "benutzername": benutzername,
                "sam_account": sam_account,
                "upn": upn,
                "abteilung": abteilung,
                "externe_id": externe_id,
                "quelle": "AD",
                "distinguished_name": distinguished_name,
            })

        verbindung.unbind()

        meldung = (
            f"{len(benutzer_liste)} reale AD-Benutzer geladen. "
            f"Im AD deaktivierte Konten: {deaktivierte_ad_konten}. "
            f"Übersprungene technische/unvollständige Konten: {uebersprungene_technische_konten}. "
            f"Übersprungene Dubletten: {uebersprungene_duplikate}."
        )

        return (
            True,
            meldung,
            benutzer_liste,
            vorhandene_ad_konten,
        )

    except Exception as fehler:
        return (
            False,
            (
                "AD-Benutzer konnten nicht geladen werden: "
                f"{fehler}"
            ),
            [],
            [],
        )


def ad_benutzer_lokal_synchronisieren():
    (
        erfolgreich,
        meldung,
        ad_benutzer_liste,
        vorhandene_ad_konten,
    ) = ad_benutzer_laden()

    if not erfolgreich:
        return {
            "erfolgreich": False,
            "meldung": meldung,
            "geladen": 0,
            "neu": 0,
            "aktualisiert": 0,
            "uebersprungen": 0,
            "deaktiviert": 0,
            "fehler": 0,
        }

    verbindung = verbindung_oeffnen()
    cursor = verbindung.cursor()

    neu = 0
    aktualisiert = 0
    uebersprungen = 0
    deaktiviert = 0
    fehler = 0
    fehlerdetails = []

    aktuelle_externe_ids = {
        str(konto.get("externe_id") or "").strip().lower()
        for konto in vorhandene_ad_konten
        if not konto.get("deaktiviert")
        if str(konto.get("externe_id") or "").strip()
    }

    aktuelle_emails = {
        str(konto.get("email") or "").strip().lower()
        for konto in vorhandene_ad_konten
        if not konto.get("deaktiviert")
        if str(konto.get("email") or "").strip()
    }

    aktuelle_benutzernamen = {
        str(
            konto.get("benutzername")
            or ""
        ).strip().lower()
        for konto in vorhandene_ad_konten
        if not konto.get("deaktiviert")
        if str(
            konto.get("benutzername")
            or ""
        ).strip()
    }

    deaktivierte_externe_ids = {
        str(konto.get("externe_id") or "").strip().lower()
        for konto in vorhandene_ad_konten
        if konto.get("deaktiviert")
        and str(konto.get("externe_id") or "").strip()
    }

    deaktivierte_emails = {
        str(konto.get("email") or "").strip().lower()
        for konto in vorhandene_ad_konten
        if konto.get("deaktiviert")
        and str(konto.get("email") or "").strip()
    }

    deaktivierte_benutzernamen = {
        str(konto.get("benutzername") or "").strip().lower()
        for konto in vorhandene_ad_konten
        if konto.get("deaktiviert")
        and str(konto.get("benutzername") or "").strip()
    }

    for ad_benutzer in ad_benutzer_liste:
        cursor.execute("SAVEPOINT ad_benutzer")

        try:
            name = ad_benutzer.get("name", "").strip()
            vorname = ad_benutzer.get("vorname", "").strip()
            nachname = ad_benutzer.get("nachname", "").strip()
            benutzername = ad_benutzer.get("benutzername", "").strip()
            email = ad_benutzer.get("email", "").strip()
            abteilung = ad_benutzer.get("abteilung", "").strip()
            externe_id = ad_benutzer.get("externe_id", "").strip()

            # Bereits die Anwesenheit im AD schützt einen
            # lokalen Datensatz vor einer falschen Deaktivierung.
            if externe_id:
                aktuelle_externe_ids.add(externe_id.lower())

            if email:
                aktuelle_emails.add(email.lower())

            if benutzername:
                aktuelle_benutzernamen.add(benutzername.lower())

            if not email and not benutzername and not externe_id:
                uebersprungen += 1
                continue

            if not vorname or not nachname:
                uebersprungen += 1
                continue

            if not name:
                name = f"{vorname} {nachname}".strip()

            passende_ids = set()

            for spalte, wert in (
                ("email", email),
                ("benutzername", benutzername),
                ("externe_id", externe_id),
            ):
                if not wert:
                    continue

                treffer = cursor.execute(
                    f"""
                    SELECT id
                    FROM benutzer
                    WHERE LOWER(TRIM(COALESCE({spalte}, '')))
                        = LOWER(TRIM(?))
                    """,
                    (wert,),
                ).fetchall()
                passende_ids.update(int(eintrag[0]) for eintrag in treffer)

            if len(passende_ids) > 1:
                raise ValueError(
                    "Die AD-Kennungen passen zu mehreren lokalen Benutzern. "
                    "Der Datensatz wurde zum Schutz vor einer falschen "
                    "Zusammenführung nicht geändert."
                )

            vorhandener_benutzer = (
                (next(iter(passende_ids)),)
                if passende_ids
                else None
            )

            if vorhandener_benutzer and benutzername:
                benutzername_konflikt = cursor.execute(
                    """
                    SELECT id
                    FROM benutzer
                    WHERE benutzername = ?
                      AND id != ?
                    LIMIT 1
                    """,
                    (benutzername, vorhandener_benutzer[0]),
                ).fetchone()

                if benutzername_konflikt is not None:
                    raise ValueError(
                        "Der Benutzername wird bereits von einem anderen "
                        "lokalen Benutzer verwendet."
                    )

            if vorhandener_benutzer:
                cursor.execute("""
                    UPDATE benutzer
                    SET
                        name = ?,
                        benutzername = ?,
                        email = ?,
                        abteilung = ?,
                        quelle = ?,
                        externe_id = ?,
                        aktiv = 1,
                        deaktivierungsgrund = NULL
                    WHERE id = ?
                """, (
                    name,
                    benutzername,
                    email,
                    abteilung,
                    "AD",
                    externe_id,
                    vorhandener_benutzer[0],
                ))

                aktualisiert += 1

            else:
                cursor.execute("""
                    INSERT INTO benutzer
                        (name, benutzername, email, abteilung, aktiv, quelle, externe_id)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    benutzername,
                    email,
                    abteilung,
                    1,
                    "AD",
                    externe_id,
                ))

                neu += 1

            cursor.execute("RELEASE SAVEPOINT ad_benutzer")

        except Exception as fehler_objekt:
            cursor.execute("ROLLBACK TO SAVEPOINT ad_benutzer")
            cursor.execute("RELEASE SAVEPOINT ad_benutzer")
            fehler += 1

            benutzerkennung = (
                str(
                    ad_benutzer.get("email")
                    or ad_benutzer.get("benutzername")
                    or ad_benutzer.get("externe_id")
                    or ad_benutzer.get("name")
                    or "Unbekannter Benutzer"
                ).strip()
            )

            fehlergrund = (
                str(fehler_objekt).strip()
                or "Unbekannter Fehler"
            )

            fehlerdetails.append(
                f"{benutzerkennung}: {fehlergrund}"
            )

    cursor.execute("""
        SELECT id, email, benutzername, externe_id
        FROM benutzer
        WHERE quelle = 'AD'
          AND aktiv = 1
    """)

    lokale_ad_benutzer = cursor.fetchall()

    anzahl_vorhandene_ad_konten = len(
        vorhandene_ad_konten
    )

    anzahl_aktive_lokale_ad_benutzer = len(
        lokale_ad_benutzer
    )

    deaktivierung_erlaubt = (
        anzahl_vorhandene_ad_konten > 0
        and (
            anzahl_aktive_lokale_ad_benutzer == 0
            or anzahl_vorhandene_ad_konten
            >= anzahl_aktive_lokale_ad_benutzer * 0.5
        )
    )

    if deaktivierung_erlaubt:
        for lokaler_benutzer in lokale_ad_benutzer:
            benutzer_id = lokaler_benutzer[0]
            lokale_email = (
                lokaler_benutzer[1]
                or ""
            ).strip().lower()

            lokaler_benutzername = (
                lokaler_benutzer[2]
                or ""
            ).strip().lower()

            lokale_externe_id = (
                lokaler_benutzer[3]
                or ""
            ).strip().lower()

            ist_aktuell = (
                (
                    lokale_externe_id
                    and lokale_externe_id
                    in aktuelle_externe_ids
                )
                or (
                    lokale_email
                    and lokale_email
                    in aktuelle_emails
                )
                or (
                    lokaler_benutzername
                    and lokaler_benutzername
                    in aktuelle_benutzernamen
                )
            )

            if not ist_aktuell:
                ist_im_ad_deaktiviert = (
                    (
                        lokale_externe_id
                        and lokale_externe_id
                        in deaktivierte_externe_ids
                    )
                    or (
                        lokale_email
                        and lokale_email
                        in deaktivierte_emails
                    )
                    or (
                        lokaler_benutzername
                        and lokaler_benutzername
                        in deaktivierte_benutzernamen
                    )
                )
                deaktivierungsgrund = (
                    AD_KONTO_DEAKTIVIERT
                    if ist_im_ad_deaktiviert
                    else NICHT_IM_AD_GEFUNDEN
                )

                cursor.execute("""
                    UPDATE benutzer
                    SET
                        aktiv = 0,
                        deaktivierungsgrund = ?
                    WHERE id = ?
                """, (deaktivierungsgrund, benutzer_id))

                deaktiviert += 1

        # Bereits inaktive Datensaetze erhalten nach dem vollstaendigen
        # Abgleich ebenfalls einen aktuellen Grund. Das gilt auch fuer
        # Hinweisdatensaetze aus einer REST-Quelle, wenn ihr Konto im AD
        # eindeutig als deaktiviert erkannt wurde.
        inaktive_benutzer = cursor.execute(
            """
            SELECT id, email, benutzername, externe_id, quelle
            FROM benutzer
            WHERE aktiv = 0
            """
        ).fetchall()

        for lokaler_benutzer in inaktive_benutzer:
            lokale_email = str(lokaler_benutzer[1] or "").strip().lower()
            lokaler_benutzername = str(
                lokaler_benutzer[2] or ""
            ).strip().lower()
            lokale_externe_id = str(
                lokaler_benutzer[3] or ""
            ).strip().lower()

            ist_im_ad_deaktiviert = (
                (
                    lokale_externe_id
                    and lokale_externe_id in deaktivierte_externe_ids
                )
                or (
                    lokale_email
                    and lokale_email in deaktivierte_emails
                )
                or (
                    lokaler_benutzername
                    and lokaler_benutzername
                    in deaktivierte_benutzernamen
                )
            )
            deaktivierungsgrund = (
                AD_KONTO_DEAKTIVIERT
                if ist_im_ad_deaktiviert
                else (
                    NICHT_IM_AD_GEFUNDEN
                    if str(lokaler_benutzer[4] or "").strip().lower()
                    == "ad"
                    else ""
                )
            )

            if not deaktivierungsgrund:
                continue

            cursor.execute(
                """
                UPDATE benutzer
                SET deaktivierungsgrund = ?
                WHERE id = ?
                """,
                (deaktivierungsgrund, lokaler_benutzer[0]),
            )
    else:
        meldung += (
            " Deaktivierungen wurden aus Sicherheitsgründen "
            "übersprungen, weil der AD-Abruf leer oder "
            "auffällig unvollständig war."
        )

    deaktivierte_technische_konten = (
        _deaktiviere_technische_lokale_ad_konten(cursor)
    )
    deaktiviert += deaktivierte_technische_konten

    if deaktivierte_technische_konten:
        meldung += (
            f" {deaktivierte_technische_konten} technische oder "
            "testartige Konten wurden aus der aktiven Benutzerliste "
            "entfernt."
        )

    verbindung.commit()
    verbindung.close()

    return {
        "erfolgreich": True,
        "meldung": meldung + " Lokale Synchronisation abgeschlossen.",
        "geladen": len(ad_benutzer_liste),
        "neu": neu,
        "aktualisiert": aktualisiert,
        "uebersprungen": uebersprungen,
        "deaktiviert": deaktiviert,
        "fehler": fehler,
        "fehlerdetails": fehlerdetails,
    }

def _ad_datenquelle_id_laden():
    verbindung = verbindung_oeffnen()

    try:
        eintrag = verbindung.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE LOWER(TRIM(typ)) = 'ad'
              AND aktiv = 1
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()

        if eintrag is None:
            return None

        return int(eintrag[0])

    finally:
        verbindung.close()


def ad_benutzer_mit_protokoll_synchronisieren(
    ausgeloest_durch="manuell",
):
    datenquelle_id = _ad_datenquelle_id_laden()

    if datenquelle_id is None:
        return {
            "erfolgreich": False,
            "meldung": (
                "Die Active-Directory-Datenquelle "
                "wurde nicht gefunden."
            ),
            "geladen": 0,
            "neu": 0,
            "aktualisiert": 0,
            "uebersprungen": 0,
            "deaktiviert": 0,
            "fehler": 1,
        }

    try:
        lauf_id = synchronisationslauf_starten(
            datenquelle_id,
            ausgeloest_durch=ausgeloest_durch,
        )

    except SynchronisationLaeuftBereits as fehler:
        return {
            "erfolgreich": False,
            "bereits_aktiv": True,
            "meldung": str(fehler),
            "geladen": 0,
            "neu": 0,
            "aktualisiert": 0,
            "uebersprungen": 0,
            "deaktiviert": 0,
            "fehler": 0,
            "datenquelle_id": datenquelle_id,
        }

    try:
        ergebnis = (
            ad_benutzer_lokal_synchronisieren()
        )

        if not ergebnis.get("erfolgreich"):
            fehlermeldung = str(
                ergebnis.get(
                    "meldung",
                    "Die AD-Synchronisierung ist fehlgeschlagen.",
                )
            )

            synchronisationslauf_fehlerhaft_beenden(
                lauf_id,
                fehlermeldung,
            )

            fehler_speichern(
                datenquelle_id,
                fehlermeldung,
                lauf_id=lauf_id,
            )

            return ergebnis

        neu = int(
            ergebnis.get("neu", 0) or 0
        )
        aktualisiert = int(
            ergebnis.get("aktualisiert", 0) or 0
        )
        uebersprungen = int(
            ergebnis.get("uebersprungen", 0) or 0
        )
        deaktiviert = int(
            ergebnis.get("deaktiviert", 0) or 0
        )
        fehlerhaft = int(
            ergebnis.get("fehler", 0) or 0
        )

        meldung = (
            f"AD-Synchronisierung erfolgreich: "
            f"{neu} neu, "
            f"{aktualisiert} aktualisiert, "
            f"{deaktiviert} deaktiviert, "
            f"{uebersprungen} übersprungen, "
            f"{fehlerhaft} fehlerhaft."
        )

        fehlerdetails = ergebnis.get(
            "fehlerdetails",
            [],
        )

        fehlerdetails_text = None

        if fehlerdetails:
            fehlerdetails_text = "\n".join(
                str(eintrag)
                for eintrag in fehlerdetails
                if str(eintrag).strip()
            )

        synchronisationslauf_erfolgreich_beenden(
            lauf_id=lauf_id,
            angelegt=neu,
            aktualisiert=aktualisiert,
            deaktiviert=deaktiviert,
            unveraendert=uebersprungen,
            fehlerhaft=fehlerhaft,
            meldung=meldung,
            fehlerdetails=fehlerdetails_text,
        )

        erfolgreiche_synchronisation_speichern(
            datenquelle_id,
            lauf_id=lauf_id,
            meldung=meldung,
        )

        ergebnis["meldung"] = meldung
        ergebnis["datenquelle_id"] = (
            datenquelle_id
        )
        ergebnis["lauf_id"] = lauf_id

        return ergebnis

    except Exception as fehler:
        fehlermeldung = (
            str(fehler).strip()
            or (
                "Unbekannter Fehler bei der "
                "AD-Synchronisierung."
            )
        )

        try:
            synchronisationslauf_fehlerhaft_beenden(
                lauf_id,
                fehlermeldung,
            )
        except Exception:
            pass

        try:
            fehler_speichern(
                datenquelle_id,
                fehlermeldung,
            )
        except Exception:
            pass

        return {
            "erfolgreich": False,
            "meldung": fehlermeldung,
            "geladen": 0,
            "neu": 0,
            "aktualisiert": 0,
            "uebersprungen": 0,
            "deaktiviert": 0,
            "fehler": 1,
            "datenquelle_id": datenquelle_id,
            "lauf_id": lauf_id,
        }
