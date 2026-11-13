from demo.database import connect as demo_connection
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import sqlite3
from datenquelle_service import DATENBANK_DATEI


ZEITFORMAT = "%Y-%m-%d %H:%M:%S"
ANZEIGE_ZEITZONE = ZoneInfo("Europe/Berlin")


def verbindung_oeffnen():
    return demo_connection(DATENBANK_DATEI)



class SynchronisationLaeuftBereits(Exception):
    pass


def aktuelle_zeit():
    return datetime.now(
        timezone.utc
    ).strftime(ZEITFORMAT)


def zeit_in_sekunden(sekunden):
    return (
        datetime.now(timezone.utc)
        + timedelta(seconds=sekunden)
    ).strftime(ZEITFORMAT)


def _datenquelle_id_ermitteln(datenquelle):
    if datenquelle is None:
        return None

    try:
        datenquelle_id = int(datenquelle)
    except (TypeError, ValueError):
        datenquelle_id = None

    verbindung = verbindung_oeffnen()

    try:
        if datenquelle_id is not None:
            eintrag = verbindung.execute(
                """
                SELECT id
                FROM datenquellen
                WHERE id = ?
                """,
                (datenquelle_id,),
            ).fetchone()

            if eintrag is not None:
                return int(eintrag[0])

            return None

        suchwert = str(
            datenquelle
        ).strip().lower()

        if not suchwert:
            return None

        eintrag = verbindung.execute(
            """
            SELECT id
            FROM datenquellen
            WHERE LOWER(TRIM(typ)) = ?
               OR LOWER(TRIM(name)) = ?
            ORDER BY
                aktiv DESC,
                id ASC
            LIMIT 1
            """,
            (
                suchwert,
                suchwert,
            ),
        ).fetchone()

        if eintrag is None:
            return None

        return int(eintrag[0])

    finally:
        verbindung.close()


def _leerer_status(datenquelle_id=None):
    return {
        "datenquelle_id": datenquelle_id,
        "letzte_synchronisation": None,
        "letzter_fehler": None,
        "naechster_erlaubter_abruf": None,
        "status": "nie_synchronisiert",
        "aktualisiert_am": None,
    }


def status_laden(datenquelle):
    datenquelle_id = _datenquelle_id_ermitteln(
        datenquelle
    )

    if datenquelle_id is None:
        return _leerer_status()

    verbindung = verbindung_oeffnen()

    try:
        eintrag = verbindung.execute(
            """
            SELECT
                datenquelle_id,
                letzte_synchronisation,
                letzter_fehler,
                naechster_erlaubter_abruf,
                status,
                aktualisiert_am
            FROM synchronisation_status
            WHERE datenquelle_id = ?
            """,
            (datenquelle_id,),
        ).fetchone()

    finally:
        verbindung.close()

    if eintrag is None:
        return _leerer_status(
            datenquelle_id=datenquelle_id
        )

    return {
        "datenquelle_id": eintrag[0],
        "letzte_synchronisation": eintrag[1],
        "letzter_fehler": eintrag[2],
        "naechster_erlaubter_abruf": eintrag[3],
        "status": eintrag[4],
        "aktualisiert_am": eintrag[5],
    }


def status_speichern(
    datenquelle,
    status,
    letzte_synchronisation=None,
    letzter_fehler=None,
    naechster_erlaubter_abruf=None,
    lauf_id=None,
    datenquellen_status=None,
    meldung=None,
):
    datenquelle_id = _datenquelle_id_ermitteln(
        datenquelle
    )

    if datenquelle_id is None:
        raise ValueError(
            "Die Datenquelle konnte nicht ermittelt werden."
        )

    verbindung = verbindung_oeffnen()

    try:
        verbindung.execute(
            "BEGIN IMMEDIATE"
        )

        if lauf_id is not None:
            lauf = verbindung.execute(
                """
                SELECT datenquelle_id
                FROM synchronisationslaeufe
                WHERE id = ?
                """,
                (int(lauf_id),),
            ).fetchone()

            if lauf is None:
                verbindung.rollback()
                return False

            if int(lauf[0]) != datenquelle_id:
                verbindung.rollback()
                return False

            neuerer_lauf = verbindung.execute(
                """
                SELECT id
                FROM synchronisationslaeufe
                WHERE datenquelle_id = ?
                  AND id > ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    datenquelle_id,
                    int(lauf_id),
                ),
            ).fetchone()

            if neuerer_lauf is not None:
                verbindung.rollback()
                return False

        verbindung.execute(
            """
            INSERT INTO synchronisation_status (
                datenquelle_id,
                letzte_synchronisation,
                letzter_fehler,
                naechster_erlaubter_abruf,
                status,
                aktualisiert_am
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(datenquelle_id) DO UPDATE SET
                letzte_synchronisation =
                    excluded.letzte_synchronisation,
                letzter_fehler =
                    excluded.letzter_fehler,
                naechster_erlaubter_abruf =
                    excluded.naechster_erlaubter_abruf,
                status =
                    excluded.status,
                aktualisiert_am =
                    CURRENT_TIMESTAMP
            """,
            (
                datenquelle_id,
                letzte_synchronisation,
                letzter_fehler,
                naechster_erlaubter_abruf,
                str(status),
            ),
        )

        if datenquellen_status is not None:
            verbindung.execute(
                """
                UPDATE datenquellen
                SET
                    status = ?,
                    letzte_meldung = ?,
                    aktualisiert_am = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    str(datenquellen_status),
                    str(meldung or ""),
                    datenquelle_id,
                ),
            )

        verbindung.commit()
        return True

    except Exception:
        verbindung.rollback()
        raise

    finally:
        verbindung.close()


def erfolgreiche_synchronisation_speichern(
    datenquelle,
    lauf_id=None,
    meldung=None,
):
    return status_speichern(
        datenquelle=datenquelle,
        status="ok",
        letzte_synchronisation=aktuelle_zeit(),
        letzter_fehler=None,
        naechster_erlaubter_abruf=None,
        lauf_id=lauf_id,
        datenquellen_status="verbunden",
        meldung=(
            meldung
            or "Synchronisierung erfolgreich abgeschlossen."
        ),
    )


def fehler_speichern(
    datenquelle,
    fehlermeldung,
    lauf_id=None,
):
    status_alt = status_laden(
        datenquelle
    )

    return status_speichern(
        datenquelle=datenquelle,
        status="fehler",
        letzte_synchronisation=status_alt.get(
            "letzte_synchronisation"
        ),
        letzter_fehler=str(
            fehlermeldung
        ),
        naechster_erlaubter_abruf=status_alt.get(
            "naechster_erlaubter_abruf"
        ),
        lauf_id=lauf_id,
        datenquellen_status="fehler",
        meldung=str(fehlermeldung),
    )


def rate_limit_speichern(
    datenquelle,
    retry_after_sekunden,
    lauf_id=None,
):
    status_alt = status_laden(
        datenquelle
    )

    return status_speichern(
        datenquelle=datenquelle,
        status="rate_limit",
        letzte_synchronisation=status_alt.get(
            "letzte_synchronisation"
        ),
        letzter_fehler=(
            "Rate Limit erreicht. "
            f"Retry-After: {retry_after_sekunden} "
            "Sekunden."
        ),
        naechster_erlaubter_abruf=(
            zeit_in_sekunden(
                int(retry_after_sekunden)
            )
        ),
        lauf_id=lauf_id,
    )


def abruf_erlaubt(
    datenquelle,
    mindest_stunden=24,
):
    status = status_laden(
        datenquelle
    )

    naechster_erlaubter_abruf = status.get(
        "naechster_erlaubter_abruf"
    )
    letzte_synchronisation = status.get(
        "letzte_synchronisation"
    )

    jetzt = datetime.now(
        timezone.utc
    ).replace(
        tzinfo=None
    )

    if naechster_erlaubter_abruf:
        try:
            naechster_zeitpunkt = datetime.strptime(
                naechster_erlaubter_abruf,
                ZEITFORMAT,
            )

            if jetzt < naechster_zeitpunkt:
                return (
                    False,
                    "Abruf wegen Rate Limit erst ab "
                    f"{naechster_erlaubter_abruf} "
                    "erlaubt.",
                )

        except ValueError:
            pass

    if letzte_synchronisation:
        try:
            letzte_zeit = datetime.strptime(
                letzte_synchronisation,
                ZEITFORMAT,
            )

            naechster_regulaerer_abruf = (
                letzte_zeit
                + timedelta(
                    hours=mindest_stunden
                )
            )

            if jetzt < naechster_regulaerer_abruf:
                return (
                    False,
                    "Letzte Synchronisation war vor "
                    f"weniger als {mindest_stunden} "
                    "Stunden.",
                )

        except ValueError:
            pass

    return True, "Abruf erlaubt."




def _zeitpunkt_anzeigen(wert):
    if not wert:
        return ""

    try:
        zeitpunkt = datetime.strptime(
            wert,
            ZEITFORMAT,
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return wert

    zeitpunkt = zeitpunkt.astimezone(ANZEIGE_ZEITZONE)
    heute = datetime.now(ANZEIGE_ZEITZONE).date()

    if zeitpunkt.date() == heute:
        return zeitpunkt.strftime("Heute um %H:%M Uhr")

    if (heute - zeitpunkt.date()).days == 1:
        return zeitpunkt.strftime("Gestern um %H:%M Uhr")

    return zeitpunkt.strftime("%d.%m.%Y um %H:%M Uhr")


def synchronisationslaeufe_laden(
    limit=10,
    datenquelle_id=None,
):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 10

    limit = max(1, min(limit, 100))

    parameter = []
    filter_sql = ""

    if datenquelle_id is not None:
        try:
            datenquelle_id = int(
                datenquelle_id
            )
        except (TypeError, ValueError):
            return []

        filter_sql = (
            "WHERE lauf.datenquelle_id = ?"
        )
        parameter.append(
            datenquelle_id
        )

    parameter.append(
        limit
    )

    verbindung = verbindung_oeffnen()

    try:
        zeilen = verbindung.execute(
            f"""
            SELECT
                lauf.id,
                lauf.datenquelle_id,
                quelle.name,
                quelle.typ,
                lauf.status,
                lauf.gestartet_am,
                lauf.beendet_am,
                lauf.angelegt,
                lauf.aktualisiert,
                lauf.deaktiviert,
                lauf.unveraendert,
                lauf.fehlerhaft,
                lauf.meldung,
                lauf.fehlerdetails,
                lauf.ausgeloest_durch,
                lauf.zuweisungen_verarbeitet,
                lauf.zuweisungen_neu,
                lauf.zuweisungen_reaktiviert,
                lauf.zuweisungen_bereits_aktiv,
                lauf.zuweisungen_deaktiviert,
                lauf.zuweisungen_fehlerhaft,
                lauf.zuweisungen_nicht_gefunden,
                lauf.zuweisungen_mehrdeutig,
                lauf.konfliktdetails_json
            FROM synchronisationslaeufe AS lauf
            LEFT JOIN datenquellen AS quelle
                ON quelle.id = lauf.datenquelle_id
            {filter_sql}
            ORDER BY lauf.id DESC
            LIMIT ?
            """,
            tuple(parameter),
        ).fetchall()

    finally:
        verbindung.close()

    ergebnisse = []

    for zeile in zeilen:
        gestartet_am = zeile[5]
        beendet_am = zeile[6]
        dauer_sekunden = None

        if gestartet_am and beendet_am:
            try:
                gestartet = datetime.strptime(
                    gestartet_am,
                    ZEITFORMAT,
                )
                beendet = datetime.strptime(
                    beendet_am,
                    ZEITFORMAT,
                )

                dauer_sekunden = max(
                    0,
                    int(
                        (
                            beendet
                            - gestartet
                        ).total_seconds()
                    ),
                )

            except ValueError:
                dauer_sekunden = None

        konfliktdetails = (
            json.loads(zeile[23])
            if zeile[23]
            else []
        )

        # Department differences are reconciliation hints.  They do not
        # prevent a matched user from receiving its license and therefore
        # must not fill the actionable conflict list.  Filtering here also
        # keeps older runs (which stored these hints as conflicts) readable.
        if isinstance(konfliktdetails, list):
            konfliktdetails = [
                konflikt
                for konflikt in konfliktdetails
                if not (
                    isinstance(konflikt, dict)
                    and konflikt.get("typ")
                    == "abweichende_abteilung"
                )
            ]

            # Ältere REST-Läufe haben technische Produktmodule einzeln als
            # fehlende Lizenzen aufgeführt. Für die Bedienoberfläche genügt
            # eine verständliche Zusammenfassung; die gespeicherten
            # Laufdaten selbst bleiben unverändert.
            alte_lizenzkonflikte = [
                konflikt
                for konflikt in konfliktdetails
                if isinstance(konflikt, dict)
                and konflikt.get("typ") == "lizenz_nicht_gefunden"
            ]
            if alte_lizenzkonflikte:
                konfliktdetails = [
                    konflikt
                    for konflikt in konfliktdetails
                    if not (
                        isinstance(konflikt, dict)
                        and konflikt.get("typ") == "lizenz_nicht_gefunden"
                    )
                ]
                konfliktdetails.append({
                    "typ": "lizenzzuordnung_nicht_eindeutig",
                    "anzahl_zuweisungen": sum(
                        int(konflikt.get("anzahl_zuweisungen", 0) or 0)
                        for konflikt in alte_lizenzkonflikte
                    ),
                    "meldung": (
                        "Die gelieferten Angaben konnten damals keiner "
                        "eindeutigen Lizenz zugeordnet werden."
                    ),
                })
        else:
            konfliktdetails = []

        ergebnisse.append({
            "id": zeile[0],
            "datenquelle_id": zeile[1],
            "datenquelle_name": (
                zeile[2]
                or "Unbekannte Datenquelle"
            ),
            "datenquelle_typ": (
                zeile[3]
                or ""
            ),
            "status": zeile[4],
            "gestartet_am": gestartet_am,
            "gestartet_anzeige": _zeitpunkt_anzeigen(
                gestartet_am
            ),
            "beendet_am": beendet_am,
            "beendet_anzeige": _zeitpunkt_anzeigen(
                beendet_am
            ),
            "dauer_sekunden": dauer_sekunden,
            "angelegt": int(
                zeile[7] or 0
            ),
            "aktualisiert": int(
                zeile[8] or 0
            ),
            "deaktiviert": int(
                zeile[9] or 0
            ),
            "unveraendert": int(
                zeile[10] or 0
            ),
            "fehlerhaft": int(
                zeile[11] or 0
            ),
            "meldung": zeile[12] or "",
            "fehlerdetails": zeile[13] or "",
            "ausgeloest_durch": (
                zeile[14]
                or "manuell"
            ),
            "zuweisungen_verarbeitet": int(
                zeile[15] or 0
            ),
            "zuweisungen_neu": int(
                zeile[16] or 0
            ),
            "zuweisungen_reaktiviert": int(
                zeile[17] or 0
            ),
            "zuweisungen_bereits_aktiv": int(
                zeile[18] or 0
            ),
            "zuweisungen_deaktiviert": int(
                zeile[19] or 0
            ),
            "zuweisungen_fehlerhaft": int(
                zeile[20] or 0
            ),
            "zuweisungen_nicht_gefunden": int(
                zeile[21] or 0
            ),
            "zuweisungen_mehrdeutig": int(
                zeile[22] or 0
            ),
            "konfliktdetails": konfliktdetails,
            "zuweisungen_konflikte": len(
                konfliktdetails
            ),
        })

    return ergebnisse

def synchronisationslauf_starten(
    datenquelle,
    ausgeloest_durch="manuell",
    maximale_laufzeit_minuten=30,
):
    datenquelle_id = _datenquelle_id_ermitteln(
        datenquelle
    )

    if datenquelle_id is None:
        raise ValueError(
            "Die Datenquelle konnte nicht ermittelt werden."
        )

    verbindung = verbindung_oeffnen()

    try:
        verbindung.execute(
            "BEGIN IMMEDIATE"
        )

        maximale_laufzeit = int(
            maximale_laufzeit_minuten
        )

        if maximale_laufzeit <= 0:
            raise ValueError(
                "Die maximale Laufzeit muss größer als 0 sein."
            )

        verbindung.execute(
            """
            UPDATE synchronisationslaeufe
            SET
                status = 'fehler',
                beendet_am = CURRENT_TIMESTAMP,
                meldung = ?,
                fehlerdetails = ?
            WHERE datenquelle_id = ?
              AND status = 'laeuft'
              AND datetime(gestartet_am) <= datetime(
                  'now',
                  ?
              )
            """,
            (
                "Synchronisationslauf automatisch beendet.",
                (
                    "Der Synchronisationslauf wurde nach einer "
                    "Zeitüberschreitung automatisch beendet."
                ),
                datenquelle_id,
                f"-{maximale_laufzeit} minutes",
            ),
        )

        aktiver_lauf = verbindung.execute(
            """
            SELECT
                id,
                gestartet_am
            FROM synchronisationslaeufe
            WHERE datenquelle_id = ?
              AND status = 'laeuft'
            ORDER BY id DESC
            LIMIT 1
            """,
            (datenquelle_id,),
        ).fetchone()

        if aktiver_lauf is not None:
            verbindung.rollback()

            raise SynchronisationLaeuftBereits(
                "Für diese Datenquelle läuft bereits "
                "eine Synchronisierung."
            )

        cursor = verbindung.execute(
            """
            INSERT INTO synchronisationslaeufe (
                datenquelle_id,
                status,
                ausgeloest_durch
            )
            VALUES (?, 'laeuft', ?)
            """,
            (
                datenquelle_id,
                str(
                    ausgeloest_durch
                    or "manuell"
                ),
            ),
        )

        lauf_id = cursor.lastrowid
        verbindung.commit()

        return int(lauf_id)

    except SynchronisationLaeuftBereits:
        raise

    except Exception:
        verbindung.rollback()
        raise

    finally:
        verbindung.close()


def synchronisationslauf_erfolgreich_beenden(
    lauf_id,
    angelegt=0,
    aktualisiert=0,
    deaktiviert=0,
    unveraendert=0,
    fehlerhaft=0,
    meldung=None,
    fehlerdetails=None,
    zuweisungen_verarbeitet=0,
    zuweisungen_neu=0,
    zuweisungen_reaktiviert=0,
    zuweisungen_bereits_aktiv=0,
    zuweisungen_deaktiviert=0,
    zuweisungen_fehlerhaft=0,
    zuweisungen_nicht_gefunden=0,
    zuweisungen_mehrdeutig=0,
    konfliktdetails=None,
    teilweise_erfolgreich=False,
):
    fehlerhaft = int(fehlerhaft or 0)

    zuweisungs_konflikte = (
        int(zuweisungen_fehlerhaft or 0)
        + int(zuweisungen_nicht_gefunden or 0)
        + int(zuweisungen_mehrdeutig or 0)
    )

    status = (
        "teilweise_erfolgreich"
        if (
            bool(teilweise_erfolgreich)
            or fehlerhaft > 0
            or zuweisungs_konflikte > 0
        )
        else "ok"
    )

    verbindung = verbindung_oeffnen()

    try:
        verbindung.execute(
            """
            UPDATE synchronisationslaeufe
            SET
                status = ?,
                beendet_am = CURRENT_TIMESTAMP,
                angelegt = ?,
                aktualisiert = ?,
                deaktiviert = ?,
                unveraendert = ?,
                fehlerhaft = ?,
                meldung = ?,
                fehlerdetails = ?,
                zuweisungen_verarbeitet = ?,
                zuweisungen_neu = ?,
                zuweisungen_reaktiviert = ?,
                zuweisungen_bereits_aktiv = ?,
                zuweisungen_deaktiviert = ?,
                zuweisungen_fehlerhaft = ?,
                zuweisungen_nicht_gefunden = ?,
                zuweisungen_mehrdeutig = ?,
                konfliktdetails_json = ?
            WHERE id = ?
              AND status = 'laeuft'
            """,
            (
                status,
                int(angelegt or 0),
                int(aktualisiert or 0),
                int(deaktiviert or 0),
                int(unveraendert or 0),
                fehlerhaft,
                meldung,
                (
                    str(fehlerdetails)
                    if fehlerdetails
                    else None
                ),
                int(zuweisungen_verarbeitet or 0),
                int(zuweisungen_neu or 0),
                int(zuweisungen_reaktiviert or 0),
                int(zuweisungen_bereits_aktiv or 0),
                int(zuweisungen_deaktiviert or 0),
                int(zuweisungen_fehlerhaft or 0),
                int(zuweisungen_nicht_gefunden or 0),
                int(zuweisungen_mehrdeutig or 0),
                json.dumps(
                    konfliktdetails or [],
                    ensure_ascii=False,
                ),
                int(lauf_id),
            ),
        )

        verbindung.commit()

    finally:
        verbindung.close()


def synchronisationslauf_fehlerhaft_beenden(
    lauf_id,
    fehlermeldung,
):
    verbindung = verbindung_oeffnen()

    try:
        verbindung.execute(
            """
            UPDATE synchronisationslaeufe
            SET
                status = 'fehler',
                beendet_am = CURRENT_TIMESTAMP,
                meldung =
                    'Synchronisierung fehlgeschlagen.',
                fehlerdetails = ?
            WHERE id = ?
              AND status = 'laeuft'
            """,
            (
                str(fehlermeldung),
                int(lauf_id),
            ),
        )

        verbindung.commit()

    finally:
        verbindung.close()
