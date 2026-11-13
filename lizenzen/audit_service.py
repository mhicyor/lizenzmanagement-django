from .models import LizenzAenderung


FELDER = (
    ("name", "Name", 1),
    ("anbieter", "Anbieter", 2),
    ("anzahl", "Anzahl", 3),
    ("kosten", "Kosten pro Lizenz", 5),
    ("ablaufdatum", "Ablaufdatum", 6),
    ("verlaengerungsdatum", "Verlängerungsdatum", 7),
    ("kostenmodell", "Kostenmodell", 10),
    ("kategorie", "Kategorie", 13),
    ("beschreibung", "Beschreibung", 17),
    ("datenquelle", "Datenquelle", 18),
    ("status", "Status", 21),
)


def lizenz_snapshot(lizenz):
    if not lizenz:
        return {}

    snapshot = {}

    for schluessel, anzeigename, index in FELDER:
        wert = lizenz[index] if len(lizenz) > index else None
        snapshot[schluessel] = {
            "label": anzeigename,
            "wert": wert if wert not in (None, "") else "—",
        }

    return snapshot


def _benutzername(user):
    voller_name = user.get_full_name().strip()
    return voller_name or user.get_username()


def lizenz_erstellt_protokollieren(user, lizenz):
    snapshot = lizenz_snapshot(lizenz)
    aenderungen = {
        eintrag["label"]: {
            "alt": "—",
            "neu": eintrag["wert"],
        }
        for eintrag in snapshot.values()
    }

    return LizenzAenderung.objects.create(
        lizenz_id=lizenz[0],
        lizenz_name=lizenz[1],
        aktion=LizenzAenderung.AKTION_ERSTELLT,
        ausgefuehrt_von=user,
        ausgefuehrt_von_name=_benutzername(user),
        aenderungen=aenderungen,
    )


def lizenz_bearbeitung_protokollieren(user, vorher, nachher):
    vorher_snapshot = lizenz_snapshot(vorher)
    nachher_snapshot = lizenz_snapshot(nachher)
    aenderungen = {}

    for schluessel, nachher_eintrag in nachher_snapshot.items():
        vorher_eintrag = vorher_snapshot.get(schluessel, {})
        alter_wert = vorher_eintrag.get("wert", "—")
        neuer_wert = nachher_eintrag["wert"]

        if alter_wert != neuer_wert:
            aenderungen[nachher_eintrag["label"]] = {
                "alt": alter_wert,
                "neu": neuer_wert,
            }

    if not aenderungen:
        return None

    return LizenzAenderung.objects.create(
        lizenz_id=nachher[0],
        lizenz_name=nachher[1],
        aktion=LizenzAenderung.AKTION_BEARBEITET,
        ausgefuehrt_von=user,
        ausgefuehrt_von_name=_benutzername(user),
        aenderungen=aenderungen,
    )


def lizenz_historie_laden(lizenz_id):
    return LizenzAenderung.objects.filter(lizenz_id=lizenz_id).select_related(
        "ausgefuehrt_von"
    )
