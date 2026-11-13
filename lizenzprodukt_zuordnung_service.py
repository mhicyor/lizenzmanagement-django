from typing import Any

from gruppen_mapping_service import (
    gruppen_mapping_laden,
)
from lizenz_erkennungsregel_service import (
    lizenz_erkennungsregeln_laden,
)


RELEVANTE_KLASSIFIKATIONEN = {
    "produktprofil",
    "mapping_kandidat",
}


def offene_lizenzprodukt_zuordnungen_laden(
    datenquelle_id: int,
) -> list[dict[str, Any]]:
    gruppen = gruppen_mapping_laden(
        datenquelle_id
    )

    regeln = lizenz_erkennungsregeln_laden(
        datenquelle_id
    )

    offene = []

    for gruppe in gruppen:
        klassifikation = gruppe.get(
            "klassifikation"
        )

        if klassifikation not in RELEVANTE_KLASSIFIKATIONEN:
            continue

        gruppenname = str(
            gruppe.get("gruppenname", "")
        ).strip()

        if not gruppenname:
            continue

        passende_regeln = []

        for regel in regeln:
            muster = str(
                regel.get("muster", "")
            ).strip().lower()

            if muster and muster in gruppenname.lower():
                passende_regeln.append(regel)

        if passende_regeln:
            continue

        offene.append(
            {
                "mapping_id": gruppe["id"],
                "gruppenname": gruppenname,
                "klassifikation": klassifikation,
                "vorschlag": "",
                "aktion": "zuordnen",
            }
        )

    return offene


def produktkandidaten_mit_entscheidungen_laden(
    datenquelle_id: int,
    produktkandidaten: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gruppen = gruppen_mapping_laden(datenquelle_id)
    regeln = lizenz_erkennungsregeln_laden(datenquelle_id)

    gruppen_nach_name = {
        str(gruppe.get("gruppenname", "")).strip().lower(): gruppe
        for gruppe in gruppen
        if str(gruppe.get("gruppenname", "")).strip()
    }
    regeln_nach_muster = {
        str(regel.get("muster", "")).strip().lower(): regel
        for regel in regeln
        if str(regel.get("muster", "")).strip()
    }

    ergebnis = []

    for produkt in produktkandidaten:
        produkt_mit_entscheidung = dict(produkt)
        externe_gruppen = produkt.get("externe_gruppen", [])

        if not isinstance(externe_gruppen, list):
            externe_gruppen = []

        gruppen_entscheidungen = []

        for gruppenname in externe_gruppen:
            schluessel = str(gruppenname or "").strip().lower()
            mapping = gruppen_nach_name.get(schluessel)
            regel = regeln_nach_muster.get(schluessel)

            if mapping and mapping.get("klassifikation") == "ignorieren":
                gruppen_entscheidungen.append(("ignorieren", None))
                continue

            lizenz_id = None

            if mapping and mapping.get("lizenz_id"):
                lizenz_id = int(mapping["lizenz_id"])
            elif regel and regel.get("lizenz_id"):
                lizenz_id = int(regel["lizenz_id"])

            if lizenz_id:
                gruppen_entscheidungen.append(("vorhanden", lizenz_id))
            else:
                gruppen_entscheidungen.append(("offen", None))

        if (
            gruppen_entscheidungen
            and all(
                entscheidung[0] == "ignorieren"
                for entscheidung in gruppen_entscheidungen
            )
        ):
            produkt_mit_entscheidung[
                "gespeicherte_aktion"
            ] = "ignorieren"
        elif gruppen_entscheidungen:
            lizenz_ids = {
                entscheidung[1]
                for entscheidung in gruppen_entscheidungen
                if entscheidung[0] == "vorhanden"
            }

            if (
                len(lizenz_ids) == 1
                and all(
                    entscheidung[0] == "vorhanden"
                    for entscheidung in gruppen_entscheidungen
                )
            ):
                produkt_mit_entscheidung[
                    "gespeicherte_aktion"
                ] = "vorhanden"
                produkt_mit_entscheidung[
                    "gespeicherte_lizenz_id"
                ] = lizenz_ids.pop()

        ergebnis.append(produkt_mit_entscheidung)

    return ergebnis
