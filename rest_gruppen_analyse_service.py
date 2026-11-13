from collections import Counter
from typing import Any


PRODUKT_HINTS = (
    "acrobat",
    "creative cloud",
    "all apps",
    "photoshop",
    "illustrator",
    "indesign",
    "premiere",
    "after effects",
    "lightroom",
    "audition",
    "animate",
    "dreamweaver",
    "stock",
    "sign",
    "pro edition",
    "standardkonfiguration",
    "license",
    "licensed",
    "licence",
    "lizenz",
    "subscription",
    "abonnement",
    "entitlement",
    "product profile",
    "productprofile",
    "produktprofil",
    "service plan",
    "serviceplan",
    "premium",
    "professional",
    "enterprise",
    "business",
    "cloud",
    "suite",
    "software",
)


TECHNISCHE_HINTS = (
    "_admin",
    "-admin",
    " admin",
    "admins",
    "administrator",
    "admin_group",
    "product_admin",
    "deployment_admin",
    "support_admin",
    "technical account",
    "service account",
    "servicekonto",
)


def _normalisieren(wert: str) -> str:
    return str(wert or "").strip().lower()


def _enthaelt_abteilung(
    gruppenname: str,
    bekannte_abteilungen: list[str],
) -> bool:
    text = _normalisieren(gruppenname)

    for abteilung in bekannte_abteilungen:
        abteilung_text = _normalisieren(abteilung)

        if not abteilung_text:
            continue

        if abteilung_text in text:
            return True

    return False


def gruppe_klassifizieren(
    gruppenname: str,
    bekannte_abteilungen: list[str] | None = None,
) -> str:
    bekannte_abteilungen = bekannte_abteilungen or []
    text = _normalisieren(gruppenname)

    technische_gruppe = (
        text.startswith("_")
        or any(
            hinweis in text
            for hinweis in TECHNISCHE_HINTS
        )
    )

    if technische_gruppe:
        return "technisch"

    enthaelt_produkt = any(
        hinweis in text
        for hinweis in PRODUKT_HINTS
    )

    enthaelt_abteilung = _enthaelt_abteilung(
        gruppenname,
        bekannte_abteilungen,
    )

    if enthaelt_produkt and enthaelt_abteilung:
        return "mapping_kandidat"

    if enthaelt_produkt:
        return "produktprofil"

    return "organisation"


def gruppen_aus_benutzer_daten_analysieren(
    datensaetze: list[dict[str, Any]],
    gruppen_feld: str,
    bekannte_abteilungen: list[str] | None = None,
) -> dict[str, Any]:
    bekannte_abteilungen = bekannte_abteilungen or []
    zaehler = Counter()

    for datensatz in datensaetze:
        if not isinstance(datensatz, dict):
            continue

        gruppen = datensatz.get(gruppen_feld)

        if isinstance(gruppen, list):
            for gruppe in gruppen:
                if gruppe:
                    zaehler[str(gruppe).strip()] += 1

        elif gruppen:
            zaehler[str(gruppen).strip()] += 1

    gruppen = []

    for name, anzahl in zaehler.most_common():
        klassifikation = gruppe_klassifizieren(
            name,
            bekannte_abteilungen,
        )

        gruppen.append(
            {
                "name": name,
                "anzahl_benutzer": anzahl,
                "klassifikation": klassifikation,
            }
        )

    return {
        "anzahl_gruppen": len(gruppen),
        "gruppen": gruppen,
        "produktprofile": [
            gruppe for gruppe in gruppen
            if gruppe["klassifikation"] == "produktprofil"
        ],
        "mapping_kandidaten": [
            gruppe for gruppe in gruppen
            if gruppe["klassifikation"] == "mapping_kandidat"
        ],
        "organisationen": [
            gruppe for gruppe in gruppen
            if gruppe["klassifikation"] == "organisation"
        ],
        "technische_gruppen": [
            gruppe for gruppe in gruppen
            if gruppe["klassifikation"] == "technisch"
        ],
    }
