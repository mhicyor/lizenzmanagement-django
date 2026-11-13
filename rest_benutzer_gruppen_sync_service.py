import json
import sqlite3
from typing import Any

from datenquelle_service import (
    DATENBANK_DATEI,
    datenquelle_mit_geheimnissen_laden,
)
from sqlite_context import sqlite_verbindung
from rest_api_service import (
    ALLE_BENUTZER_MARKER,
    rest_api_rohdaten_laden,
)
from rest_gruppen_analyse_service import (
    gruppen_aus_benutzer_daten_analysieren,
)
from gruppen_mapping_service import (
    gruppen_mapping_vorschlaege_speichern,
)
from lizenz_erkennungsregel_service import (
    lizenz_erkennungsregeln_laden,
    lizenz_aus_gruppen_erkennen,
)
from lizenz_service import (
    sync_lizenzzuweisung_speichern,
)
from sync_status_service import (
    synchronisationslauf_starten,
    synchronisationslauf_erfolgreich_beenden,
    synchronisationslauf_fehlerhaft_beenden,
)
from zuweisungs_matching_service import (
    _email_normalisieren,
    _personen_email,
    externen_deaktivierten_benutzer_speichern,
)


class RestBenutzerGruppenSyncFehler(Exception):
    pass


# Marker used by releases before direct user-license sources became
# provider-neutral.  It remains readable during migration, but new rules are
# always written with ``ALLE_BENUTZER_MARKER`` by the setup flow.
_LEGACY_DIREKTE_BENUTZER_MARKER = "__sosafe_alle_benutzer__"


def _ist_direkter_benutzer_marker(muster: Any) -> bool:
    return str(muster or "").strip().lower() in {
        ALLE_BENUTZER_MARKER,
        _LEGACY_DIREKTE_BENUTZER_MARKER,
    }


def _json_laden(wert: Any) -> dict[str, Any]:
    if isinstance(wert, dict):
        return wert

    try:
        return json.loads(wert or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _bekannte_abteilungen_laden(verbindung) -> list[str]:
    zeilen = verbindung.execute(
        """
        SELECT DISTINCT abteilung
        FROM benutzer
        WHERE abteilung IS NOT NULL
          AND TRIM(abteilung) != ''
        """
    ).fetchall()

    return [
        str(zeile["abteilung"]).strip()
        for zeile in zeilen
        if str(zeile["abteilung"]).strip()
    ]


def _benutzer_suchen(
    verbindung,
    email: str | None,
    benutzername: str | None,
):
    email = str(email or "").strip().lower()
    benutzername = str(benutzername or "").strip().lower()

    if email:
        treffer = verbindung.execute(
            """
            SELECT id, name, benutzername, email, abteilung, quelle, aktiv
            FROM benutzer
            WHERE LOWER(COALESCE(email, '')) = ?
            """,
            (email,),
        ).fetchall()

        if treffer:
            return treffer, "email"

    benutzernamen = [benutzername]
    if "@" in benutzername:
        benutzernamen.append(benutzername.split("@", 1)[0])

    for benutzername_wert in dict.fromkeys(benutzernamen):
        if not benutzername_wert:
            continue
        treffer = verbindung.execute(
            """
            SELECT id, name, benutzername, email, abteilung, quelle, aktiv
            FROM benutzer
            WHERE LOWER(COALESCE(benutzername, '')) = ?
            """,
            (benutzername_wert,),
        ).fetchall()

        if treffer:
            return treffer, "benutzername"

    return [], ""


def _wert(datensatz: dict[str, Any], feldname: str):
    if not feldname:
        return None

    return datensatz.get(feldname)


def _direkte_abteilung_lesen(wert: Any) -> str:
    """Normalize a direct source's scalar department representation."""
    if isinstance(wert, (list, tuple, set)):
        if len(wert) != 1:
            return ""
        wert = next(iter(wert))

    if isinstance(wert, dict):
        for schluessel in (
            "name",
            "displayName",
            "title",
            "value",
        ):
            if wert.get(schluessel):
                return str(wert[schluessel]).strip()
        return ""

    return str(wert or "").strip()


def _eindeutige_lizenztreffer(
    lizenztreffer: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    eindeutige_treffer = []
    gesehene_lizenz_ids = set()

    for lizenztreffer_eintrag in lizenztreffer:
        try:
            lizenz_id = int(
                lizenztreffer_eintrag.get("lizenz_id")
            )
        except (TypeError, ValueError):
            continue

        if lizenz_id in gesehene_lizenz_ids:
            continue

        gesehene_lizenz_ids.add(lizenz_id)
        eindeutige_treffer.append(
            {
                **lizenztreffer_eintrag,
                "lizenz_id": lizenz_id,
            }
        )

    return eindeutige_treffer


def _lizenz_zielarten_laden(
    lizenz_ids: set[int],
) -> dict[int, str]:
    """Lädt, ob eine Lizenz benutzer-, geräte- oder serverbezogen ist."""
    if not lizenz_ids:
        return {}

    platzhalter = ", ".join("?" for _ in lizenz_ids)

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row
        spalten = {
            spalte[1]
            for spalte in verbindung.execute(
                "PRAGMA table_info(lizenzen)"
            ).fetchall()
        }
        zuweisungsart = (
            "zuweisungsart"
            if "zuweisungsart" in spalten
            else "''"
        )
        lizenzklasse = (
            "lizenzklasse"
            if "lizenzklasse" in spalten
            else "''"
        )
        zeilen = verbindung.execute(
            f"""
            SELECT
                id,
                COALESCE(
                    NULLIF(TRIM({zuweisungsart}), ''),
                    NULLIF(TRIM({lizenzklasse}), ''),
                    'benutzer'
                ) AS zielart
            FROM lizenzen
            WHERE id IN ({platzhalter})
            """,
            tuple(lizenz_ids),
        ).fetchall()

    return {
        int(zeile["id"]): str(
            zeile["zielart"] or ""
        ).strip().lower()
        for zeile in zeilen
    }


def _personenbezogene_lizenztreffer_filtern(
    lizenztreffer: list[dict[str, Any]],
    zielart_cache: dict[int, str],
) -> tuple[list[dict[str, Any]], int]:
    """Nimmt nur Lizenztreffer, die wirklich zu Benutzern gehören."""
    fehlende_ids = {
        int(eintrag["lizenz_id"])
        for eintrag in lizenztreffer
        if int(eintrag["lizenz_id"]) not in zielart_cache
    }

    if fehlende_ids:
        zielart_cache.update(
            _lizenz_zielarten_laden(fehlende_ids)
        )

    personen_lizenzen = [
        eintrag
        for eintrag in lizenztreffer
        if zielart_cache.get(
            int(eintrag["lizenz_id"]),
            "",
        )
        == "benutzer"
    ]

    return (
        personen_lizenzen,
        len(lizenztreffer) - len(personen_lizenzen),
    )


def _zuweisungsstatus_laden(
    verbindung,
    benutzer_id: int,
    lizenz_id: int,
) -> str:
    zeile = verbindung.execute(
        """
        SELECT status
        FROM zuweisungen
        WHERE benutzer_id = ?
          AND lizenz_id = ?
        LIMIT 1
        """,
        (benutzer_id, lizenz_id),
    ).fetchone()

    if zeile is None:
        return "nicht_vorhanden"

    if str(zeile["status"] or "").strip().lower() == "aktiv":
        return "aktiv"

    return "inaktiv"


def _externe_zuweisungs_id(
    datenquelle_id: int,
    benutzer_externe_id: Any,
    benutzer_id: int,
    lizenz_id: int,
) -> str:
    externer_benutzer = str(
        benutzer_externe_id or benutzer_id
    ).strip()

    return (
        f"rest_api:{datenquelle_id}:"
        f"benutzer:{externer_benutzer}:"
        f"lizenz:{lizenz_id}"
    )


def _quellenzuweisungen_abgleichen(
    datenquelle_id: int,
    gesehene_zuweisungen: set[tuple[int, int]],
) -> int:
    """Entfernt nur Zuweisungen, die von genau dieser REST-Quelle stammen."""
    quelle = f"rest_api:{datenquelle_id}"
    deaktiviert = 0

    with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
        verbindung.row_factory = sqlite3.Row
        verbindung.execute("BEGIN IMMEDIATE")

        aktive_zuweisungen = verbindung.execute(
            """
            SELECT id, lizenz_id, ziel_id
            FROM lizenz_zuweisungen
            WHERE ziel_typ = 'benutzer'
              AND quelle = ?
              AND status = 'aktiv'
            """,
            (quelle,),
        ).fetchall()

        for zuweisung in aktive_zuweisungen:
            lizenz_id = int(zuweisung["lizenz_id"])
            benutzer_id = int(zuweisung["ziel_id"])

            if (benutzer_id, lizenz_id) in gesehene_zuweisungen:
                continue

            verbindung.execute(
                """
                UPDATE lizenz_zuweisungen
                SET
                    status = 'entfernt',
                    synchronisiert_am = DATETIME('now'),
                    entfernt_am = DATETIME('now')
                WHERE id = ?
                """,
                (zuweisung["id"],),
            )

            andere_aktive_zuweisung = verbindung.execute(
                """
                SELECT id
                FROM lizenz_zuweisungen
                WHERE lizenz_id = ?
                  AND ziel_typ = 'benutzer'
                  AND ziel_id = ?
                  AND status = 'aktiv'
                LIMIT 1
                """,
                (lizenz_id, benutzer_id),
            ).fetchone()

            if andere_aktive_zuweisung is None:
                verbindung.execute(
                    """
                    UPDATE zuweisungen
                    SET status = 'entfernt'
                    WHERE benutzer_id = ?
                      AND lizenz_id = ?
                      AND status = 'aktiv'
                    """,
                    (benutzer_id, lizenz_id),
                )

            deaktiviert += 1

        verbindung.commit()

    return deaktiviert


def rest_benutzer_gruppen_synchronisieren(
    datenquelle_id: int,
    ausgeloest_durch: str = "manuell",
) -> dict[str, Any]:
    datenquelle = datenquelle_mit_geheimnissen_laden(
        datenquelle_id
    )

    if not datenquelle:
        raise RestBenutzerGruppenSyncFehler(
            "Die Datenquelle wurde nicht gefunden."
        )

    rest_datenart = datenquelle.get(
        "rest_datenart"
    )

    datenquelle_name = str(
        datenquelle.get("name") or "Benutzerquelle"
    ).strip() or "Benutzerquelle"

    if rest_datenart not in {
        "benutzer_gruppen",
        "benutzer_lizenz",
    }:
        raise RestBenutzerGruppenSyncFehler(
            "Diese Datenquelle ist keine "
            "unterstützte Benutzer-REST-Quelle."
        )

    direkte_benutzerlizenz = (
        rest_datenart == "benutzer_lizenz"
    )

    lauf_id = synchronisationslauf_starten(
        datenquelle_id,
        ausgeloest_durch=ausgeloest_durch,
    )

    try:
        geheimnisse = datenquelle.get("geheimnisse", {})

        konfiguration = {
            **geheimnisse,
            "name": datenquelle.get("name", ""),
            "basis_url": datenquelle.get("basis_url", ""),
            "endpunkt": datenquelle.get("endpunkt", ""),
            "auth_typ": datenquelle.get("auth_typ", ""),
            "token_url": datenquelle.get("token_url", ""),
            "scope": datenquelle.get("scope", ""),
            "http_methode": "GET",
        }

        roh = rest_api_rohdaten_laden(
            konfiguration
        )

        datensaetze = roh.get("datensaetze", [])

        mapping = _json_laden(
            datenquelle.get("feld_mapping")
        )

        gruppen_feld = mapping.get(
            "lizenzname",
            "",
        )

        with sqlite_verbindung(DATENBANK_DATEI) as analyse_verbindung:
            analyse_verbindung.row_factory = sqlite3.Row
            bekannte_abteilungen = _bekannte_abteilungen_laden(
                analyse_verbindung
            )

        gruppen_analyse = gruppen_aus_benutzer_daten_analysieren(
            datensaetze,
            gruppen_feld,
            bekannte_abteilungen,
        )

        erkennungsregeln = lizenz_erkennungsregeln_laden(
            datenquelle_id
        )

        zielart_cache: dict[int, str] = {}
        direkte_lizenztreffer_roh = (
            _eindeutige_lizenztreffer(
                [
                    {
                        "gruppe": datenquelle_name,
                        "muster": regel.get(
                            "muster",
                            "",
                        ),
                        "lizenz_id": regel.get(
                            "lizenz_id"
                        ),
                        "lizenzname": regel.get(
                            "lizenzname",
                            datenquelle_name,
                        ),
                    }
                    for regel in erkennungsregeln
                    if _ist_direkter_benutzer_marker(
                        regel.get("muster", "")
                    )
                ]
            )
        )
        (
            direkte_lizenztreffer,
            direkte_nicht_personenbezogene_treffer,
        ) = _personenbezogene_lizenztreffer_filtern(
            direkte_lizenztreffer_roh,
            zielart_cache,
        )

        if (
            direkte_benutzerlizenz
            and not direkte_lizenztreffer_roh
        ):
            raise RestBenutzerGruppenSyncFehler(
                f"Für die Benutzerquelle „{datenquelle_name}“ "
                "ist noch keine passende Lizenz hinterlegt."
            )

        if (
            direkte_benutzerlizenz
            and direkte_lizenztreffer_roh
            and not direkte_lizenztreffer
        ):
            raise RestBenutzerGruppenSyncFehler(
                f"Die hinterlegte Lizenz für „{datenquelle_name}“ "
                "ist nicht personenbezogen. Bitte wähle eine "
                "Benutzerlizenz oder ändere die Lizenzart."
            )

        erkannte_lizenztreffer = 0
        benutzer_mit_lizenztreffer = 0
        nicht_erkannte_gruppen = set()
        nicht_personenbezogene_lizenztreffer = (
            direkte_nicht_personenbezogene_treffer
        )

        zuweisungen_neu = 0
        zuweisungen_bereits_aktiv = 0
        zuweisungen_reaktiviert = 0
        zuweisungen_aktualisiert = 0
        zuweisungen_fehlgeschlagen = 0
        zuweisungen_nicht_gefunden = 0
        zuweisungen_mehrdeutig = 0
        zuweisungen_deaktiviert = 0
        zuweisungsabgleich_ausgefuehrt = False

        verarbeitet = 0
        mit_email = 0
        mit_gruppen = 0
        ohne_email = 0
        ohne_gruppen = 0
        deaktiviert_erfasst = 0
        technische_datensaetze_ignoriert = 0

        benutzer_zugeordnet = 0
        benutzer_nicht_gefunden = 0
        benutzer_mehrdeutig = 0
        abteilungen_uebereinstimmend = 0
        abteilungen_abweichend = 0
        abteilungen_lokal_nicht_hinterlegt = 0

        beispiele = []
        konflikte = []
        gesehene_zuweisungen: set[tuple[int, int]] = set()
        gruppen_feld_vorhanden = False

        with sqlite_verbindung(DATENBANK_DATEI) as verbindung:
            verbindung.row_factory = sqlite3.Row
            for datensatz in datensaetze:
                if not isinstance(datensatz, dict):
                    continue

                verarbeitet += 1

                if gruppen_feld and gruppen_feld in datensatz:
                    gruppen_feld_vorhanden = True

                email = _wert(
                    datensatz,
                    mapping.get("email", ""),
                )

                benutzername = _wert(
                    datensatz,
                    mapping.get("anzahl", ""),
                )

                email = _personen_email(
                    email=email,
                    benutzername=benutzername,
                )

                gruppen = _wert(
                    datensatz,
                    mapping.get("lizenzname", ""),
                )

                status = _wert(
                    datensatz,
                    mapping.get("status", ""),
                )

                benutzer_externe_id = _wert(
                    datensatz,
                    mapping.get("externe_id", ""),
                )

                gruppen_liste = (
                    gruppen
                    if isinstance(gruppen, list)
                    else [gruppen] if gruppen else []
                )

                if direkte_benutzerlizenz:
                    lizenztreffer = list(
                        direkte_lizenztreffer
                    )
                else:
                    lizenztreffer_roh = (
                        _eindeutige_lizenztreffer(
                            lizenz_aus_gruppen_erkennen(
                                gruppen_liste,
                                erkennungsregeln,
                            )
                        )
                    )
                    (
                        lizenztreffer,
                        uebersprungene_treffer,
                    ) = _personenbezogene_lizenztreffer_filtern(
                        lizenztreffer_roh,
                        zielart_cache,
                    )
                    nicht_personenbezogene_lizenztreffer += (
                        uebersprungene_treffer
                    )

                if lizenztreffer:
                    benutzer_mit_lizenztreffer += 1
                    erkannte_lizenztreffer += len(lizenztreffer)
                elif not direkte_benutzerlizenz:
                    for gruppe in gruppen_liste:
                        if gruppe:
                            nicht_erkannte_gruppen.add(str(gruppe))

                if gruppen:
                    mit_gruppen += 1
                else:
                    ohne_gruppen += 1

                if not lizenztreffer:
                    if len(beispiele) < 5:
                        beispiele.append(
                            {
                                "email": email,
                                "benutzername": benutzername,
                                "gruppen": gruppen,
                                "abteilung": "",
                                "status": status,
                                "lokaler_treffer": 0,
                            }
                        )
                    continue

                treffer, gefunden_ueber = _benutzer_suchen(
                    verbindung,
                    email,
                    benutzername,
                )

                if len(treffer) == 1:
                    email = _personen_email(
                        email=email,
                        benutzername=benutzername,
                        lokaler_benutzer=dict(treffer[0]),
                    )

                if email:
                    mit_email += 1
                else:
                    ohne_email += 1

                # Erst nach dem AD-Abgleich entscheiden: Ein externes Konto
                # kann ohne eigenes E-Mail-Feld trotzdem eine echte Person
                # sein, wenn der lokale AD-Treffer eine E-Mail besitzt.
                if not email:
                    technische_datensaetze_ignoriert += 1
                    if len(beispiele) < 5:
                        beispiele.append(
                            {
                                "email": "",
                                "benutzername": benutzername,
                                "gruppen": gruppen,
                                "abteilung": "",
                                "status": status,
                                "lokaler_treffer": len(treffer),
                            }
                        )
                    continue

                if not treffer:
                    benutzer_id = externen_deaktivierten_benutzer_speichern(
                        quelle=f"rest_api:{datenquelle_id}",
                        email=email,
                        externe_id=benutzer_externe_id,
                        benutzername=benutzername,
                        verbindung=verbindung,
                    )
                    if benutzer_id is not None:
                        # Die Zuweisungslogik arbeitet bewusst in einer
                        # eigenen Transaktion. Deshalb den neuen, inaktiven
                        # Hinweisdatensatz vorher freigeben.
                        verbindung.commit()
                        treffer = verbindung.execute(
                            """
                            SELECT id, name, benutzername, email,
                                   abteilung, quelle, aktiv
                            FROM benutzer
                            WHERE id = ?
                            """,
                            (benutzer_id,),
                        ).fetchall()
                        gefunden_ueber = "externe E-Mail"
                        deaktiviert_erfasst += 1

                if len(treffer) == 1:
                    benutzer_zugeordnet += 1

                    benutzer_id = int(treffer[0]["id"])

                    if direkte_benutzerlizenz:
                        externe_abteilung = _direkte_abteilung_lesen(
                            gruppen
                        )
                        lokale_abteilung = str(
                            treffer[0]["abteilung"]
                            or ""
                        ).strip()

                        if (
                            externe_abteilung
                            and lokale_abteilung
                            and externe_abteilung.lower()
                            == lokale_abteilung.lower()
                        ):
                            abteilungen_uebereinstimmend += 1
                        elif (
                            externe_abteilung
                            and lokale_abteilung
                        ):
                            abteilungen_abweichend += 1

                            # A department difference is an informational
                            # reconciliation hint, not a failed license
                            # assignment.  The user was found and the
                            # assignment can still be processed safely.  Keep
                            # the aggregate count in the result/message, but
                            # reserve ``konflikte`` for actionable errors
                            # (missing/ambiguous users or failed assignments).
                        elif externe_abteilung:
                            abteilungen_lokal_nicht_hinterlegt += 1

                    for lizenztreffer_eintrag in lizenztreffer:
                        lizenz_id = int(
                            lizenztreffer_eintrag["lizenz_id"]
                        )
                        zuweisungsstatus = _zuweisungsstatus_laden(
                            verbindung,
                            benutzer_id,
                            lizenz_id,
                        )

                        try:
                            erfolgreich, zuweisungsmeldung = (
                                sync_lizenzzuweisung_speichern(
                                    lizenz_id=lizenz_id,
                                    benutzer_id=benutzer_id,
                                    quelle=f"rest_api:{datenquelle_id}",
                                    externe_id=_externe_zuweisungs_id(
                                        datenquelle_id,
                                        benutzer_externe_id,
                                        benutzer_id,
                                        lizenz_id,
                                    ),
                                )
                            )
                        except Exception as zuweisungsfehler:
                            erfolgreich = False
                            zuweisungsmeldung = str(
                                zuweisungsfehler
                            )

                        if erfolgreich:
                            gesehene_zuweisungen.add(
                                (benutzer_id, lizenz_id)
                            )

                            if zuweisungsstatus == "inaktiv":
                                zuweisungen_reaktiviert += 1
                            elif zuweisungsstatus == "nicht_vorhanden":
                                zuweisungen_neu += 1
                            elif zuweisungsstatus == "aktiv":
                                zuweisungen_bereits_aktiv += 1
                            else:
                                zuweisungen_aktualisiert += 1
                        else:
                            zuweisungen_fehlgeschlagen += 1

                            if len(konflikte) < 20:
                                konflikte.append(
                                    {
                                        "typ": "zuweisung_fehlgeschlagen",
                                        "email": email,
                                        "benutzername": benutzername,
                                        "benutzer_id": benutzer_id,
                                        "lizenz_id": lizenz_id,
                                        "meldung": zuweisungsmeldung,
                                    }
                                )

                elif len(treffer) > 1:
                    benutzer_mehrdeutig += 1
                    zuweisungen_mehrdeutig += len(lizenztreffer)

                    if len(konflikte) < 20:
                        konflikte.append(
                            {
                                "typ": "mehrdeutig",
                                "email": email,
                                "benutzername": benutzername,
                                "trefferanzahl": len(treffer),
                                "gefunden_ueber": gefunden_ueber,
                            }
                        )

                else:
                    benutzer_nicht_gefunden += 1
                    zuweisungen_nicht_gefunden += len(lizenztreffer)

                    if len(konflikte) < 20:
                        konflikte.append(
                            {
                                "typ": "nicht_gefunden",
                                "email": email,
                                "benutzername": benutzername,
                            }
                        )

                if len(beispiele) < 5:
                    beispiele.append(
                        {
                            "email": email,
                            "benutzername": benutzername,
                            "gruppen": gruppen,
                            "abteilung": (
                                _direkte_abteilung_lesen(gruppen)
                                if direkte_benutzerlizenz
                                else ""
                            ),
                            "status": status,
                            "lokaler_treffer": len(treffer),
                        }
                    )

        abgleich_sicher = (
            verarbeitet > 0
            and gruppen_feld_vorhanden
            and benutzer_nicht_gefunden == 0
            and benutzer_mehrdeutig == 0
            and zuweisungen_fehlgeschlagen == 0
        )

        if abgleich_sicher:
            zuweisungen_deaktiviert = _quellenzuweisungen_abgleichen(
                datenquelle_id,
                gesehene_zuweisungen,
            )
            zuweisungsabgleich_ausgefuehrt = True

        if direkte_benutzerlizenz:
            neue_mapping_vorschlaege = 0
        else:
            neue_mapping_vorschlaege = (
                gruppen_mapping_vorschlaege_speichern(
                    datenquelle_id,
                    gruppen_analyse["gruppen"],
                )
            )

        if direkte_benutzerlizenz:
            meldung = (
                f"Benutzerquelle „{datenquelle_name}“ erfolgreich "
                "abgeglichen: "
                f"{verarbeitet} Benutzer verarbeitet, "
                f"{benutzer_zugeordnet} lokalen AD-Benutzern "
                "zugeordnet, "
                f"{benutzer_nicht_gefunden} nicht gefunden, "
                f"{benutzer_mehrdeutig} mehrdeutig. "
                f"{deaktiviert_erfasst} als deaktivierte Personen erfasst, "
                f"{technische_datensaetze_ignoriert} technische Datensätze "
                "ohne E-Mail ignoriert. "
                f"Abteilungen: {abteilungen_uebereinstimmend} "
                "übereinstimmend, "
                f"{abteilungen_abweichend} abweichend, "
                f"{abteilungen_lokal_nicht_hinterlegt} im AD "
                "nicht hinterlegt. "
            )
        else:
            meldung = (
                "Benutzer-Gruppen-Daten erfolgreich gelesen: "
                f"{verarbeitet} Benutzer verarbeitet, "
                f"{mit_email} mit E-Mail, "
                f"{mit_gruppen} mit Gruppen, "
                f"{benutzer_zugeordnet} lokalen Benutzern zugeordnet, "
                f"{benutzer_nicht_gefunden} nicht gefunden, "
                f"{benutzer_mehrdeutig} mehrdeutig. "
                f"{deaktiviert_erfasst} als deaktivierte Personen erfasst, "
                f"{technische_datensaetze_ignoriert} technische Datensätze "
                "ohne E-Mail ignoriert. "
                f"{gruppen_analyse['anzahl_gruppen']} unterschiedliche Gruppen erkannt, "
                f"{len(gruppen_analyse['produktprofile'])} davon mögliche Produktprofile, "
                f"{neue_mapping_vorschlaege} neue Mapping-Vorschläge gespeichert, "
            )

        meldung += (
            f"{erkannte_lizenztreffer} eindeutige Lizenztreffer über Erkennungsregeln. "
            f"{erkannte_lizenztreffer} Zuweisungen verarbeitet: "
            f"{zuweisungen_neu} neu angelegt, "
            f"{zuweisungen_bereits_aktiv} bereits aktiv, "
            f"{zuweisungen_reaktiviert} reaktiviert, "
            f"{zuweisungen_aktualisiert} aktualisiert, "
            f"{zuweisungen_deaktiviert} entfernt, "
            f"{zuweisungen_fehlgeschlagen} fehlgeschlagen, "
            f"{zuweisungen_nicht_gefunden} ohne lokalen Benutzer, "
            f"{zuweisungen_mehrdeutig} mehrdeutig."
        )

        if nicht_personenbezogene_lizenztreffer:
            meldung += (
                f" {nicht_personenbezogene_lizenztreffer} "
                "Geräte-/Server-Treffer wurden nicht als "
                "Benutzerzuweisung verarbeitet."
            )

        if not zuweisungsabgleich_ausgefuehrt:
            meldung += (
                " Der Entfernungsabgleich wurde aus Sicherheitsgründen "
                "übersprungen."
            )

        synchronisationslauf_erfolgreich_beenden(
            lauf_id=lauf_id,
            angelegt=zuweisungen_neu,
            aktualisiert=(
                zuweisungen_reaktiviert
                + zuweisungen_aktualisiert
            ),
            unveraendert=verarbeitet,
            fehlerhaft=zuweisungen_fehlgeschlagen,
            meldung=meldung,
            zuweisungen_verarbeitet=erkannte_lizenztreffer,
            zuweisungen_neu=zuweisungen_neu,
            zuweisungen_reaktiviert=zuweisungen_reaktiviert,
            zuweisungen_bereits_aktiv=zuweisungen_bereits_aktiv,
            zuweisungen_deaktiviert=zuweisungen_deaktiviert,
            zuweisungen_fehlerhaft=zuweisungen_fehlgeschlagen,
            zuweisungen_nicht_gefunden=zuweisungen_nicht_gefunden,
            zuweisungen_mehrdeutig=zuweisungen_mehrdeutig,
            konfliktdetails=konflikte,
            teilweise_erfolgreich=(
                not zuweisungsabgleich_ausgefuehrt
            ),
        )

        return {
            "status": (
                "erfolg"
                if zuweisungsabgleich_ausgefuehrt
                else "teilweise_erfolgreich"
            ),
            "meldung": meldung,
            "datenquelle_id": datenquelle_id,
            "datenquelle_name": datenquelle.get("name", ""),
            "typ": "rest_api",
            "rest_datenart": rest_datenart,
            "verarbeitet": verarbeitet,
            "mit_email": mit_email,
            "mit_gruppen": mit_gruppen,
            "ohne_email": ohne_email,
            "ohne_gruppen": ohne_gruppen,
            "deaktiviert_erfasst": deaktiviert_erfasst,
            "technische_datensaetze_ignoriert": (
                technische_datensaetze_ignoriert
            ),
            "benutzer_zugeordnet": benutzer_zugeordnet,
            "benutzer_nicht_gefunden": benutzer_nicht_gefunden,
            "benutzer_mehrdeutig": benutzer_mehrdeutig,
            "abteilungen_uebereinstimmend": (
                abteilungen_uebereinstimmend
            ),
            "abteilungen_abweichend": (
                abteilungen_abweichend
            ),
            "abteilungen_lokal_nicht_hinterlegt": (
                abteilungen_lokal_nicht_hinterlegt
            ),
            "beispiele": beispiele,
            "konflikte": konflikte,
            "gruppen_analyse": gruppen_analyse,
            "neue_mapping_vorschlaege": neue_mapping_vorschlaege,
            "erkannte_lizenztreffer": erkannte_lizenztreffer,
            "benutzer_mit_lizenztreffer": benutzer_mit_lizenztreffer,
            "nicht_personenbezogene_lizenztreffer": (
                nicht_personenbezogene_lizenztreffer
            ),
            "nicht_erkannte_gruppen": sorted(nicht_erkannte_gruppen),
            "zuweisungen_neu": zuweisungen_neu,
            "zuweisungen_bereits_aktiv": zuweisungen_bereits_aktiv,
            "zuweisungen_reaktiviert": zuweisungen_reaktiviert,
            "zuweisungen_aktualisiert": zuweisungen_aktualisiert,
            "zuweisungen_fehlgeschlagen": zuweisungen_fehlgeschlagen,
            "zuweisungen_nicht_gefunden": zuweisungen_nicht_gefunden,
            "zuweisungen_mehrdeutig": zuweisungen_mehrdeutig,
            "zuweisungen_deaktiviert": zuweisungen_deaktiviert,
            "zuweisungsabgleich_ausgefuehrt": (
                zuweisungsabgleich_ausgefuehrt
            ),
            "angelegt": zuweisungen_neu,
            "aktualisiert": (
                zuweisungen_reaktiviert
                + zuweisungen_aktualisiert
            ),
            "deaktiviert": zuweisungen_deaktiviert,
            "unveraendert": verarbeitet,
            "fehlerhaft": zuweisungen_fehlgeschlagen,
        }

    except Exception as fehler:
        synchronisationslauf_fehlerhaft_beenden(
            lauf_id,
            str(fehler),
        )

        raise RestBenutzerGruppenSyncFehler(
            str(fehler)
        ) from fehler
