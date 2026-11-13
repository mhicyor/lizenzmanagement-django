from typing import Any

from ad_service import (
    ad_benutzer_mit_protokoll_synchronisieren,
)
from csv_sync_service import (
    CsvSyncFehler,
    csv_datenquelle_synchronisieren,
)
from datenquelle_service import (
    datenquelle_laden,
    faellige_automatische_datenquellen_laden,
    naechste_automatische_synchronisation_planen,
)
from rest_sync_service import (
    RestSyncFehler,
    rest_datenquelle_synchronisieren,
)
from rest_benutzer_gruppen_sync_service import (
    RestBenutzerGruppenSyncFehler,
    rest_benutzer_gruppen_synchronisieren,
)
class SyncOrchestratorFehler(Exception):
    pass


def _datenquelle_pruefen(
    datenquelle_id: int | str,
) -> tuple[int, dict[str, Any]]:
    try:
        datenquelle_id_int = int(
            datenquelle_id
        )
    except (TypeError, ValueError) as fehler:
        raise SyncOrchestratorFehler(
            "Die Datenquellen-ID ist ungültig."
        ) from fehler

    datenquelle = datenquelle_laden(
        datenquelle_id_int
    )

    if not datenquelle:
        raise SyncOrchestratorFehler(
            "Die Datenquelle wurde nicht gefunden."
        )

    if not bool(
        datenquelle.get("aktiv", 0)
    ):
        raise SyncOrchestratorFehler(
            "Die Datenquelle ist deaktiviert."
        )

    return datenquelle_id_int, datenquelle


def _rest_synchronisieren(
    datenquelle_id: int,
    datenquelle: dict[str, Any],
    ausgeloest_durch: str,
) -> dict[str, Any]:
    if datenquelle.get("rest_datenart") in {
        "benutzer_gruppen",
        "benutzer_lizenz",
    }:
        try:
            return rest_benutzer_gruppen_synchronisieren(
                datenquelle_id,
                ausgeloest_durch=ausgeloest_durch,
            )
        except RestBenutzerGruppenSyncFehler as fehler:
            raise SyncOrchestratorFehler(
                str(fehler)
            ) from fehler

    try:
        rest_ergebnis = (
            rest_datenquelle_synchronisieren(
                datenquelle_id,
                ausgeloest_durch=ausgeloest_durch,
            )
        )
    except RestSyncFehler as fehler:
        raise SyncOrchestratorFehler(
            str(fehler)
        ) from fehler

    zuweisungen = rest_ergebnis.get(
        "zuweisungen",
        {},
    )

    konflikt_anzahl = (
        int(zuweisungen.get("nicht_gefunden", 0) or 0)
        + int(zuweisungen.get("mehrdeutig", 0) or 0)
        + int(zuweisungen.get("fehlerhaft", 0) or 0)
    )

    status = (
        "teilweise_erfolgreich"
        if konflikt_anzahl
        or int(rest_ergebnis.get("fehlerhaft", 0) or 0)
        else "erfolg"
    )

    meldung_start = (
        "Synchronisierung teilweise erfolgreich: "
        if status == "teilweise_erfolgreich"
        else "Synchronisierung erfolgreich: "
    )

    meldung = (
        meldung_start
        + f"{rest_ergebnis.get('angelegt', 0)} angelegt, "
        + f"{rest_ergebnis.get('aktualisiert', 0)} aktualisiert, "
        + f"{rest_ergebnis.get('deaktiviert', 0)} deaktiviert, "
        + f"{rest_ergebnis.get('unveraendert', 0)} unverändert, "
        + f"{rest_ergebnis.get('fehlerhaft', 0)} fehlerhaft"
    )

    if zuweisungen.get("aktiv"):
        meldung += (
            f"; {zuweisungen.get('verarbeitet', 0)} "
            "Zuweisungen verarbeitet"
        )

        if konflikt_anzahl:
            meldung += (
                f", {zuweisungen.get('bereits_aktiv', 0)} bereits aktiv"
                f", {zuweisungen.get('nicht_gefunden', 0)} nicht gefunden"
                f", {zuweisungen.get('mehrdeutig', 0)} mehrdeutig"
                f", {zuweisungen.get('fehlerhaft', 0)} fehlerhaft"
            )

    meldung += "."

    return {
        "status": status,
        "meldung": meldung,
        "datenquelle_id": datenquelle_id,
        "datenquelle_name": datenquelle.get(
            "name",
            "",
        ),
        "typ": "rest_api",
        "angelegt": rest_ergebnis.get(
            "angelegt",
            0,
        ),
        "aktualisiert": rest_ergebnis.get(
            "aktualisiert",
            0,
        ),
        "deaktiviert": rest_ergebnis.get(
            "deaktiviert",
            0,
        ),
        "unveraendert": rest_ergebnis.get(
            "unveraendert",
            0,
        ),
        "fehlerhaft": rest_ergebnis.get(
            "fehlerhaft",
            0,
        ),
        "zuweisungen": zuweisungen,
        "konflikte": zuweisungen.get(
            "konflikte",
            [],
        ),
        "details": rest_ergebnis.get(
            "meldungen",
            [],
        ),
    }


def datenquelle_synchronisieren(
    datenquelle_id: int | str,
    ausgeloest_durch: str = "manuell",
) -> dict[str, Any]:
    (
        datenquelle_id_int,
        datenquelle,
    ) = _datenquelle_pruefen(
        datenquelle_id
    )

    typ = str(
        datenquelle.get("typ", "")
    ).strip().lower()

    if typ == "csv":
        try:
            csv_ergebnis = (
                csv_datenquelle_synchronisieren(
                    datenquelle_id_int,
                    ausgeloest_durch=(
                        ausgeloest_durch
                    ),
                )
            )
        except CsvSyncFehler as fehler:
            raise SyncOrchestratorFehler(
                str(fehler)
            ) from fehler

        meldung = (
            "CSV-Synchronisierung erfolgreich: "
            f"{csv_ergebnis['angelegt']} angelegt, "
            f"{csv_ergebnis['aktualisiert']} "
            "aktualisiert, "
            f"{csv_ergebnis['deaktiviert']} "
            "deaktiviert, "
            f"{csv_ergebnis['unveraendert']} "
            "unverändert, "
            f"{csv_ergebnis['fehlerhaft']} "
            "fehlerhaft."
        )

        return {
            "status": "erfolg",
            "meldung": meldung,
            "datenquelle_id": (
                datenquelle_id_int
            ),
            "datenquelle_name": (
                datenquelle.get(
                    "name",
                    "",
                )
            ),
            "typ": "csv",
            **csv_ergebnis,
        }

    if typ == "rest_api":
        return _rest_synchronisieren(
            datenquelle_id_int,
            datenquelle,
            ausgeloest_durch,
        )

    if typ == "adobe":
        raise SyncOrchestratorFehler(
            "Adobe wird nicht mehr als eigene "
            "Sonderintegration synchronisiert. "
            "Bitte Adobe als REST-API-Datenquelle "
            "einrichten und über die generische "
            "REST-Synchronisation verwenden."
        )

    if typ == "ad":
        ergebnis = (
            ad_benutzer_mit_protokoll_synchronisieren(
                ausgeloest_durch=ausgeloest_durch,
            )
        )

        if not ergebnis.get("erfolgreich"):
            raise SyncOrchestratorFehler(
                str(
                    ergebnis.get(
                        "meldung",
                        "Die AD-Synchronisierung ist fehlgeschlagen.",
                    )
                )
            )

        return {
            "status": "erfolg",
            "meldung": ergebnis.get(
                "meldung",
                "",
            ),
            "datenquelle_id": datenquelle_id_int,
            "datenquelle_name": datenquelle.get(
                "name",
                "",
            ),
            "typ": "ad",
            "angelegt": ergebnis.get(
                "neu",
                0,
            ),
            "aktualisiert": ergebnis.get(
                "aktualisiert",
                0,
            ),
            "deaktiviert": ergebnis.get(
                "deaktiviert",
                0,
            ),
            "unveraendert": ergebnis.get(
                "uebersprungen",
                0,
            ),
            "fehlerhaft": ergebnis.get(
                "fehler",
                0,
            ),
        }

    raise SyncOrchestratorFehler(
        "Für diese Datenquelle ist noch keine "
        "Synchronisierung implementiert."
    )



def faellige_synchronisationen_ausfuehren(
) -> dict[str, Any]:
    """
    Führt alle aktuell fälligen automatischen
    Synchronisationen nacheinander aus.

    Jede Datenquelle wird unabhängig verarbeitet und
    anschließend auf den nächsten Zeitpunkt geplant.
    """
    datenquellen = (
        faellige_automatische_datenquellen_laden()
    )

    ergebnisse = []

    for datenquelle in datenquellen:
        datenquelle_id = int(
            datenquelle["id"]
        )

        try:
            ergebnis = datenquelle_synchronisieren(
                datenquelle_id,
                ausgeloest_durch="automatisch",
            )

            ergebnisse.append({
                "datenquelle_id": datenquelle_id,
                "name": datenquelle.get(
                    "name",
                    "",
                ),
                "erfolgreich": True,
                "meldung": ergebnis.get(
                    "meldung",
                    "",
                ),
            })

        except Exception as fehler:
            ergebnisse.append({
                "datenquelle_id": datenquelle_id,
                "name": datenquelle.get(
                    "name",
                    "",
                ),
                "erfolgreich": False,
                "meldung": (
                    str(fehler).strip()
                    or "Unbekannter Synchronisationsfehler."
                ),
            })

        finally:
            planungsfehler = ""

            try:
                naechster_zeitpunkt = (
                    naechste_automatische_synchronisation_planen(
                        datenquelle_id
                    )
                )
            except Exception as fehler:
                naechster_zeitpunkt = None
                planungsfehler = (
                    str(fehler).strip()
                    or (
                        "Der nächste automatische Lauf "
                        "konnte nicht geplant werden."
                    )
                )

            ergebnisse[-1][
                "naechste_synchronisation"
            ] = naechster_zeitpunkt

            ergebnisse[-1][
                "planung_erfolgreich"
            ] = not bool(planungsfehler)

            ergebnisse[-1][
                "planungsfehler"
            ] = planungsfehler

    fehlgeschlagen = sum(
        1
        for eintrag in ergebnisse
        if not eintrag.get("erfolgreich")
    )

    planungsfehler_anzahl = sum(
        1
        for eintrag in ergebnisse
        if not eintrag.get(
            "planung_erfolgreich",
            True,
        )
    )

    return {
        "gefunden": len(datenquellen),
        "erfolgreich": (
            len(datenquellen)
            - fehlgeschlagen
        ),
        "fehlgeschlagen": fehlgeschlagen,
        "planungsfehler": planungsfehler_anzahl,
        "ergebnisse": ergebnisse,
    }
