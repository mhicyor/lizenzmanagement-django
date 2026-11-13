import hashlib
import sqlite3
from typing import Any

from benutzer_matching_service import (
    externen_benutzer_abgleichen,
)
from benutzer_status_service import NICHT_IM_AD_GEFUNDEN
from datenquelle_service import DATENBANK_DATEI
from sqlite_context import sqlite_verbindung


def _email_normalisieren(wert: Any) -> str:
    """Liefert nur eine einfache, belastbare E-Mail-Adresse zurück."""
    email = str(wert or "").strip().lower()

    if email.count("@") != 1 or any(zeichen.isspace() for zeichen in email):
        return ""

    lokaler_teil, domain = email.split("@", 1)
    if not lokaler_teil or not domain:
        return ""

    return email


def _personen_email(
    *,
    email: Any = None,
    benutzername: Any = None,
    lokaler_benutzer: dict[str, Any] | None = None,
) -> str:
    """Ermittelt eine Personen-E-Mail aus generischen Anmeldedaten.

    Manche APIs liefern die E-Mail als Anmeldenamen beziehungsweise UPN.
    Bei einem eindeutigen lokalen Treffer darf außerdem dessen bereits aus
    dem AD bekannte E-Mail verwendet werden.
    """
    kandidaten = [email, benutzername]
    if lokaler_benutzer:
        kandidaten.append(lokaler_benutzer.get("email"))

    for kandidat in kandidaten:
        normalisiert = _email_normalisieren(kandidat)
        if normalisiert:
            return normalisiert

    return ""


def _name_aus_email(email: str) -> tuple[str, str, str]:
    lokaler_teil = email.split("@", 1)[0]
    teile = [
        teil
        for teil in lokaler_teil.replace("-", ".").replace("_", ".").split(".")
        if teil
    ]
    lesbare_teile = [teil[:1].upper() + teil[1:] for teil in teile]
    name = " ".join(lesbare_teile).strip() or email
    vorname = lesbare_teile[0] if lesbare_teile else ""
    nachname = " ".join(lesbare_teile[1:]) if len(lesbare_teile) > 1 else ""
    return name, vorname, nachname


def externen_deaktivierten_benutzer_speichern(
    *,
    quelle: str,
    email: Any,
    externe_id: Any = None,
    benutzername: Any = None,
    verbindung: sqlite3.Connection | None = None,
) -> int | None:
    """Erfasst eine reale externe Person, die lokal beziehungsweise im AD fehlt.

    Der Datensatz bleibt bewusst inaktiv. Eine spätere AD-Synchronisation kann
    ihn über die E-Mail-Adresse erkennen und mit den echten AD-Daten ergänzen.
    Datensätze ohne E-Mail werden hier grundsätzlich nicht angelegt.
    """
    email = _email_normalisieren(email)
    quelle = str(quelle or "").strip()
    externe_id = str(externe_id or "").strip()
    benutzername = str(benutzername or "").strip()

    if not email or not quelle or quelle == "manuell":
        return None

    if "\\" in benutzername:
        benutzername = benutzername.rsplit("\\", 1)[-1]
    if "@" in benutzername:
        benutzername = benutzername.split("@", 1)[0]

    def speichern(aktive_verbindung: sqlite3.Connection) -> int:
        zu_speichernder_benutzername = benutzername
        aktive_verbindung.row_factory = sqlite3.Row
        vorhanden = aktive_verbindung.execute(
            """
            SELECT id
            FROM benutzer
            WHERE LOWER(TRIM(COALESCE(email, ''))) = LOWER(?)
            ORDER BY id
            LIMIT 1
            """,
            (email,),
        ).fetchone()

        if vorhanden is not None:
            return int(vorhanden["id"])

        if zu_speichernder_benutzername:
            benutzername_belegt = aktive_verbindung.execute(
                """
                SELECT 1
                FROM benutzer
                WHERE LOWER(TRIM(benutzername)) = LOWER(?)
                LIMIT 1
                """,
                (zu_speichernder_benutzername,),
            ).fetchone()
            if benutzername_belegt is not None:
                zu_speichernder_benutzername = ""

        if not zu_speichernder_benutzername:
            namensschluessel = hashlib.sha256(
                f"{quelle}|{email}".encode("utf-8")
            ).hexdigest()[:16]
            zu_speichernder_benutzername = f"extern-{namensschluessel}"

        name, vorname, nachname = _name_aus_email(email)
        cursor = aktive_verbindung.execute(
            """
            INSERT INTO benutzer (
                name,
                vorname,
                nachname,
                benutzername,
                email,
                abteilung,
                aktiv,
                quelle,
                externe_id,
                zuletzt_synchronisiert,
                deaktivierungsgrund
            )
            VALUES (?, ?, ?, ?, ?, '', 0, ?, ?, DATETIME('now'), ?)
            """,
            (
                name,
                vorname,
                nachname,
                zu_speichernder_benutzername,
                email,
                quelle,
                externe_id or None,
                NICHT_IM_AD_GEFUNDEN,
            ),
        )
        return int(cursor.lastrowid)

    if verbindung is not None:
        return speichern(verbindung)

    with sqlite_verbindung(DATENBANK_DATEI) as neue_verbindung:
        return speichern(neue_verbindung)


def _lizenz_laden(
    lizenz_id: int | str,
) -> dict[str, Any] | None:
    try:
        lizenz_id = int(lizenz_id)
    except (TypeError, ValueError):
        return None

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeile = verbindung.execute(
            """
            SELECT
                id,
                name,
                anzahl,
                status,
                datenquelle,
                datenquelle_id,
                api_sync_aktiv
            FROM lizenzen
            WHERE id = ?
            """,
            (lizenz_id,),
        ).fetchone()

    return dict(zeile) if zeile else None


def _zuweisungsstatus_laden(
    *,
    lizenz_id: int,
    benutzer_id: int,
) -> str:
    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        verbindung.row_factory = sqlite3.Row

        zeile = verbindung.execute(
            """
            SELECT status
            FROM lizenz_zuweisungen
            WHERE lizenz_id = ?
              AND ziel_typ = 'benutzer'
              AND ziel_id = ?
            ORDER BY
                CASE
                    WHEN status = 'aktiv' THEN 0
                    ELSE 1
                END,
                id DESC
            LIMIT 1
            """,
            (
                lizenz_id,
                benutzer_id,
            ),
        ).fetchone()

    if zeile is None:
        return "nicht_vorhanden"

    if str(
        zeile["status"] or ""
    ).strip().lower() == "aktiv":
        return "aktiv"

    return "inaktiv"


def externe_zuweisungen_vorschau(
    *,
    lizenz_id: int | str,
    datensaetze: list[dict[str, Any]],
) -> dict[str, Any]:
    lizenz = _lizenz_laden(
        lizenz_id
    )

    if lizenz is None:
        return {
            "lizenz": None,
            "gefunden": 0,
            "neu_zuweisen": 0,
            "reaktivieren": 0,
            "bereits_aktiv": 0,
            "nicht_gefunden": 0,
            "mehrdeutig": 0,
            "keine_suchdaten": 0,
            "fehler": (
                "Die ausgewählte Lizenz existiert nicht."
            ),
            "datensaetze": [],
        }

    ergebnis_datensaetze = []

    gefunden = 0
    neu_zuweisen = 0
    reaktivieren = 0
    bereits_aktiv = 0
    nicht_gefunden = 0
    mehrdeutig = 0
    keine_suchdaten = 0
    deaktiviert_erfasst = 0
    ohne_email_ignoriert = 0

    for datensatz in datensaetze:
        email = _personen_email(
            email=datensatz.get("email"),
            benutzername=datensatz.get("benutzername"),
        )
        matching = externen_benutzer_abgleichen(
            externe_id=datensatz.get(
                "benutzer_externe_id"
            ),
            email=email,
            benutzername=datensatz.get(
                "benutzername"
            ),
        )

        if matching.get("status") == "gefunden":
            email = _personen_email(
                email=email,
                benutzername=datensatz.get("benutzername"),
                lokaler_benutzer=matching.get("benutzer"),
            )

        if not email:
            ohne_email_ignoriert += 1
            matching = {
                "status": "ohne_email_ignoriert",
                "benutzer": None,
                "trefferanzahl": 0,
                "gefunden_ueber": None,
                "meldung": (
                    "Der technische Datensatz wurde ohne E-Mail-Adresse "
                    "nicht als Person übernommen."
                ),
            }

        status = matching.get("status")
        zuweisungsstatus = None

        if status == "ohne_email_ignoriert":
            aktion = "ohne_email_ignorieren"

        elif status == "gefunden":
            gefunden += 1

            benutzer_id = matching[
                "benutzer"
            ]["id"]

            zuweisungsstatus = (
                _zuweisungsstatus_laden(
                    lizenz_id=lizenz["id"],
                    benutzer_id=benutzer_id,
                )
            )

            if zuweisungsstatus == "aktiv":
                bereits_aktiv += 1
                aktion = "bereits_aktiv"

            elif zuweisungsstatus == "inaktiv":
                reaktivieren += 1
                aktion = "reaktivieren"

            else:
                neu_zuweisen += 1
                aktion = "neu_zuweisen"

        elif status == "mehrdeutig":
            mehrdeutig += 1
            aktion = "konflikt"

        elif status == "keine_suchdaten":
            keine_suchdaten += 1
            aktion = "fehlerhaft"

        else:
            # Eine Person mit E-Mail und aktiver externer Lizenz ist ein
            # fachlicher Hinweis, kein Synchronisationskonflikt. Sie wird
            # lokal inaktiv erfasst und erscheint dadurch in „Deaktivierte
            # Benutzer“. Das externe System und AD bleiben unverändert.
            deaktiviert_erfasst += 1
            aktion = "deaktiviert_erfassen"

        konflikt = None

        if aktion == "konflikt":
            konflikt = {
                "typ": "mehrdeutiger_benutzer",
                "email": datensatz.get("email"),
                "benutzername": datensatz.get("benutzername"),
                "benutzer_externe_id": datensatz.get(
                    "benutzer_externe_id"
                ),
                "trefferanzahl": matching.get(
                    "trefferanzahl"
                ),
                "gefunden_ueber": matching.get(
                    "gefunden_ueber"
                ),
                "meldung": matching.get("meldung"),
            }

        ergebnis_datensaetze.append(
            {
                **datensatz,
                "email": email,
                "aktion": aktion,
                "matching_status": status,
                "zuweisungsstatus": (
                    zuweisungsstatus
                ),
                "konflikt": konflikt,
                "benutzer_id": (
                    matching.get("benutzer") or {}
                ).get("id"),
                "benutzer": matching.get(
                    "benutzer"
                ),
                "gefunden_ueber": matching.get(
                    "gefunden_ueber"
                ),
                "trefferanzahl": matching.get(
                    "trefferanzahl"
                ),
                "meldung": matching.get(
                    "meldung"
                ),
            }
        )

    return {
        "lizenz": lizenz,
        "gefunden": gefunden,
        "neu_zuweisen": neu_zuweisen,
        "reaktivieren": reaktivieren,
        "bereits_aktiv": bereits_aktiv,
        "nicht_gefunden": nicht_gefunden,
        "mehrdeutig": mehrdeutig,
        "keine_suchdaten": keine_suchdaten,
        "deaktiviert_erfasst": deaktiviert_erfasst,
        "ohne_email_ignoriert": ohne_email_ignoriert,
        "fehler": None,
        "datensaetze": ergebnis_datensaetze,
    }


def externe_zuweisung_speichern(
    *,
    lizenz_id: int | str,
    quelle: str,
    benutzer_externe_id: Any = None,
    email: Any = None,
    benutzername: Any = None,
    zuweisung_externe_id: Any = None,
) -> dict[str, Any]:
    from lizenz_service import (
        sync_lizenzzuweisung_speichern,
    )

    quelle = str(
        quelle or ""
    ).strip()

    if not quelle or quelle == "manuell":
        return {
            "erfolgreich": False,
            "aktion": "fehlerhaft",
            "benutzer_id": None,
            "meldung": (
                "Für eine externe Zuweisung ist eine "
                "gültige Datenquelle erforderlich."
            ),
        }

    vorschau = externe_zuweisungen_vorschau(
        lizenz_id=lizenz_id,
        datensaetze=[
            {
                "benutzer_externe_id": (
                    benutzer_externe_id
                ),
                "email": email,
                "benutzername": benutzername,
            }
        ],
    )

    if vorschau.get("fehler"):
        return {
            "erfolgreich": False,
            "aktion": "fehlerhaft",
            "benutzer_id": None,
            "meldung": vorschau["fehler"],
        }

    datensatz = vorschau["datensaetze"][0]
    aktion = datensatz["aktion"]
    benutzer_id = datensatz.get(
        "benutzer_id"
    )

    if aktion == "bereits_aktiv":
        return {
            "erfolgreich": True,
            "aktion": "bereits_aktiv",
            "benutzer_id": benutzer_id,
            "meldung": (
                "Die Lizenzzuweisung ist bereits aktiv."
            ),
        }

    if aktion == "ohne_email_ignorieren":
        return {
            "erfolgreich": True,
            "aktion": "ohne_email_ignoriert",
            "benutzer_id": None,
            "meldung": datensatz.get("meldung"),
        }

    deaktiviert_erfasst = False
    if aktion == "deaktiviert_erfassen":
        benutzer_id = externen_deaktivierten_benutzer_speichern(
            quelle=quelle,
            email=datensatz.get("email"),
            externe_id=benutzer_externe_id,
            benutzername=benutzername,
        )
        if benutzer_id is None:
            return {
                "erfolgreich": False,
                "aktion": "fehlerhaft",
                "benutzer_id": None,
                "meldung": (
                    "Die externe Person konnte nicht als deaktivierter "
                    "Hinweis erfasst werden."
                ),
            }
        deaktiviert_erfasst = True
        aktion = "neu_zuweisen"

    if aktion not in {
        "neu_zuweisen",
        "reaktivieren",
    }:
        return {
            "erfolgreich": False,
            "aktion": aktion,
            "benutzer_id": benutzer_id,
            "meldung": datensatz.get(
                "meldung"
            ),
        }

    erfolgreich, meldung = (
        sync_lizenzzuweisung_speichern(
            lizenz_id=int(lizenz_id),
            benutzer_id=int(benutzer_id),
            quelle=quelle,
            externe_id=str(
                zuweisung_externe_id or ""
            ).strip() or None,
        )
    )

    return {
        "erfolgreich": bool(erfolgreich),
        "aktion": (
            aktion
            if erfolgreich
            else "fehlerhaft"
        ),
        "benutzer_id": benutzer_id,
        "deaktiviert_erfasst": deaktiviert_erfasst,
        "meldung": meldung,
    }


def externe_zuweisungen_speichern(
    *,
    lizenz_id: int | str,
    quelle: str,
    datensaetze: list[dict[str, Any]],
    vollstaendiger_abzug: bool = False,
) -> dict[str, Any]:
    """
    Verarbeitet eine vollständige Liste gelieferter
    externer Benutzerzuweisungen.

    In diesem Schritt werden nur neue Zuweisungen
    angelegt und inaktive Zuweisungen reaktiviert.
    Nicht mehr gelieferte Zuweisungen werden noch
    nicht deaktiviert.
    """
    quelle = str(
        quelle or ""
    ).strip()

    if not quelle or quelle == "manuell":
        return {
            "erfolgreich": False,
            "lizenz": None,
            "neu_zugewiesen": 0,
            "reaktiviert": 0,
            "bereits_aktiv": 0,
            "nicht_gefunden": 0,
            "mehrdeutig": 0,
            "fehlerhaft": len(datensaetze),
            "deaktiviert": 0,
            "deaktiviert_erfasst": 0,
            "ohne_email_ignoriert": 0,
            "meldung": (
                "Für externe Zuweisungen ist eine "
                "gültige Datenquelle erforderlich."
            ),
            "datensaetze": [],
        }

    vorschau = externe_zuweisungen_vorschau(
        lizenz_id=lizenz_id,
        datensaetze=datensaetze,
    )

    if vorschau.get("fehler"):
        return {
            "erfolgreich": False,
            "lizenz": None,
            "neu_zugewiesen": 0,
            "reaktiviert": 0,
            "bereits_aktiv": 0,
            "nicht_gefunden": 0,
            "mehrdeutig": 0,
            "fehlerhaft": len(datensaetze),
            "deaktiviert": 0,
            "deaktiviert_erfasst": 0,
            "ohne_email_ignoriert": 0,
            "meldung": vorschau["fehler"],
            "datensaetze": [],
        }

    neu_zugewiesen = 0
    reaktiviert = 0
    bereits_aktiv = 0
    nicht_gefunden = 0
    mehrdeutig = 0
    fehlerhaft = 0
    deaktiviert_erfasst = 0
    ohne_email_ignoriert = 0
    ergebnis_datensaetze = []

    for datensatz in vorschau["datensaetze"]:
        aktion = datensatz.get(
            "aktion"
        )

        if aktion == "bereits_aktiv":
            bereits_aktiv += 1

            ergebnis_datensaetze.append(
                {
                    **datensatz,
                    "erfolgreich": True,
                }
            )
            continue

        if aktion == "ohne_email_ignorieren":
            ohne_email_ignoriert += 1
            ergebnis_datensaetze.append(
                {
                    **datensatz,
                    "erfolgreich": True,
                }
            )
            continue

        if aktion == "nicht_gefunden":
            nicht_gefunden += 1

            ergebnis_datensaetze.append(
                {
                    **datensatz,
                    "erfolgreich": False,
                }
            )
            continue

        if aktion == "konflikt":
            mehrdeutig += 1

            ergebnis_datensaetze.append(
                {
                    **datensatz,
                    "erfolgreich": False,
                }
            )
            continue

        if aktion == "fehlerhaft":
            fehlerhaft += 1

            ergebnis_datensaetze.append(
                {
                    **datensatz,
                    "erfolgreich": False,
                }
            )
            continue

        speicherergebnis = (
            externe_zuweisung_speichern(
                lizenz_id=lizenz_id,
                quelle=quelle,
                benutzer_externe_id=(
                    datensatz.get(
                        "benutzer_externe_id"
                    )
                ),
                email=datensatz.get(
                    "email"
                ),
                benutzername=datensatz.get(
                    "benutzername"
                ),
                zuweisung_externe_id=(
                    datensatz.get(
                        "zuweisung_externe_id"
                    )
                ),
            )
        )

        gespeicherte_aktion = (
            speicherergebnis.get("aktion")
        )

        if speicherergebnis.get("deaktiviert_erfasst"):
            deaktiviert_erfasst += 1

        if (
            speicherergebnis.get("erfolgreich")
            and gespeicherte_aktion
            == "neu_zuweisen"
        ):
            neu_zugewiesen += 1

        elif (
            speicherergebnis.get("erfolgreich")
            and gespeicherte_aktion
            == "reaktivieren"
        ):
            reaktiviert += 1

        elif (
            speicherergebnis.get("erfolgreich")
            and gespeicherte_aktion
            == "bereits_aktiv"
        ):
            bereits_aktiv += 1

        else:
            fehlerhaft += 1

        ergebnis_datensaetze.append(
            {
                **datensatz,
                "erfolgreich": (
                    speicherergebnis.get(
                        "erfolgreich"
                    )
                ),
                "gespeicherte_aktion": (
                    gespeicherte_aktion
                ),
                "speichermeldung": (
                    speicherergebnis.get(
                        "meldung"
                    )
                ),
            }
        )

    deaktiviert = 0

    if vollstaendiger_abzug:
        gelieferte_externe_ids = {
            str(
                datensatz.get(
                    "zuweisung_externe_id"
                )
                or ""
            ).strip()
            for datensatz in vorschau["datensaetze"]
            if datensatz.get("aktion") != "ohne_email_ignorieren"
            if str(
                datensatz.get(
                    "zuweisung_externe_id"
                )
                or ""
            ).strip()
        }

        deaktiviert = (
            nicht_mehr_gelieferte_zuweisungen_deaktivieren(
                lizenz_id=lizenz_id,
                quelle=quelle,
                gelieferte_externe_ids=(
                    gelieferte_externe_ids
                ),
            )
        )

    erfolgreich = (
        fehlerhaft == 0
        and mehrdeutig == 0
        and nicht_gefunden == 0
    )

    meldung = (
        "Externe Zuweisungen verarbeitet: "
        f"{neu_zugewiesen} neu zugewiesen, "
        f"{reaktiviert} reaktiviert, "
        f"{bereits_aktiv} bereits aktiv, "
        f"{deaktiviert} deaktiviert, "
        f"{deaktiviert_erfasst} als deaktivierte Personen erfasst, "
        f"{ohne_email_ignoriert} technische Datensätze ignoriert, "
        f"{nicht_gefunden} nicht gefunden, "
        f"{mehrdeutig} mehrdeutig, "
        f"{fehlerhaft} fehlerhaft."
    )

    return {
        "erfolgreich": erfolgreich,
        "lizenz": vorschau["lizenz"],
        "neu_zugewiesen": neu_zugewiesen,
        "reaktiviert": reaktiviert,
        "bereits_aktiv": bereits_aktiv,
        "nicht_gefunden": nicht_gefunden,
        "mehrdeutig": mehrdeutig,
        "fehlerhaft": fehlerhaft,
        "deaktiviert": deaktiviert,
        "deaktiviert_erfasst": deaktiviert_erfasst,
        "ohne_email_ignoriert": ohne_email_ignoriert,
        "meldung": meldung,
        "datensaetze": ergebnis_datensaetze,
    }


def nicht_mehr_gelieferte_zuweisungen_deaktivieren(
    *,
    lizenz_id: int | str,
    quelle: str,
    gelieferte_externe_ids: set[str],
) -> int:
    try:
        lizenz_id = int(
            lizenz_id
        )
    except (TypeError, ValueError):
        return 0

    quelle = str(
        quelle or ""
    ).strip()

    if not quelle or quelle == "manuell":
        return 0

    externe_ids = {
        str(externe_id or "").strip()
        for externe_id in gelieferte_externe_ids
        if str(externe_id or "").strip()
    }

    with sqlite_verbindung(
        DATENBANK_DATEI
    ) as verbindung:
        if externe_ids:
            platzhalter = ", ".join(
                "?"
                for _ in externe_ids
            )

            parameter = [
                lizenz_id,
                quelle,
                *sorted(externe_ids),
            ]

            cursor = verbindung.execute(
                f"""
                UPDATE lizenz_zuweisungen
                SET
                    status = 'inaktiv',
                    entfernt_am = DATETIME('now'),
                    synchronisiert_am = DATETIME('now')
                WHERE lizenz_id = ?
                  AND ziel_typ = 'benutzer'
                  AND quelle = ?
                  AND status = 'aktiv'
                  AND TRIM(
                      COALESCE(externe_id, '')
                  ) != ''
                  AND externe_id NOT IN (
                      {platzhalter}
                  )
                """,
                parameter,
            )

        else:
            cursor = verbindung.execute(
                """
                UPDATE lizenz_zuweisungen
                SET
                    status = 'inaktiv',
                    entfernt_am = DATETIME('now'),
                    synchronisiert_am = DATETIME('now')
                WHERE lizenz_id = ?
                  AND ziel_typ = 'benutzer'
                  AND quelle = ?
                  AND status = 'aktiv'
                  AND TRIM(
                      COALESCE(externe_id, '')
                  ) != ''
                """,
                (
                    lizenz_id,
                    quelle,
                ),
            )

        deaktiviert = max(
            0,
            cursor.rowcount,
        )

        if deaktiviert:
            verbindung.execute(
                """
                UPDATE zuweisungen
                SET status = 'inaktiv'
                WHERE lizenz_id = ?
                  AND benutzer_id IN (
                      SELECT ziel_id
                      FROM lizenz_zuweisungen
                      WHERE lizenz_id = ?
                        AND ziel_typ = 'benutzer'
                        AND quelle = ?
                        AND status = 'inaktiv'
                        AND entfernt_am IS NOT NULL
                  )
                """,
                (
                    lizenz_id,
                    lizenz_id,
                    quelle,
                ),
            )

        verbindung.commit()

    return deaktiviert
