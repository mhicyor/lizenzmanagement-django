LIZENZKLASSEN = [
    ("benutzer", "Benutzerlizenz"),
    ("geraet", "Gerätelizenz"),
    ("server", "Serverlizenz"),
]


KOSTENMODELLE = [
    ("fortlaufend", "Monatlich"),
    ("jaehrlich", "Jährlich"),
    ("einmalig", "Einmalig"),
]


# Diese Listen bleiben vorerst aus Kompatibilitätsgründen bestehen,
# werden aber im neuen Fundament nicht mehr aktiv im Formular verwendet.
ZUWEISUNGSARTEN = [
    ("benutzer", "Benutzer"),
    ("geraet", "Gerät"),
    ("server", "Server"),
]


TECHNOLOGIEBEREICHE = [
    ("allgemein", "Allgemein"),
]


BEISPIEL_KLASSIFIKATIONEN = {
    "Adobe": {
        "lizenzklasse": "benutzer",
        "zuweisungsart": "benutzer",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
    "DeepL": {
        "lizenzklasse": "benutzer",
        "zuweisungsart": "benutzer",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
    "Claude": {
        "lizenzklasse": "benutzer",
        "zuweisungsart": "benutzer",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
    "VPN": {
        "lizenzklasse": "benutzer",
        "zuweisungsart": "benutzer",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
    "Sophos": {
        "lizenzklasse": "geraet",
        "zuweisungsart": "geraet",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
    "JamF": {
        "lizenzklasse": "geraet",
        "zuweisungsart": "geraet",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
    "MS Client": {
        "lizenzklasse": "geraet",
        "zuweisungsart": "geraet",
        "kostenmodell": "einmalig",
        "technologiebereich": "allgemein",
    },
    "MS Server": {
        "lizenzklasse": "server",
        "zuweisungsart": "server",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
    "MS Core CALs": {
        "lizenzklasse": "benutzer",
        "zuweisungsart": "benutzer",
        "kostenmodell": "fortlaufend",
        "technologiebereich": "allgemein",
    },
}


def anzeigename_finden(liste, wert):
    for technischer_wert, anzeigename in liste:
        if technischer_wert == wert:
            return anzeigename

    return wert or "—"


def lizenzklasse_anzeigename(wert):
    return anzeigename_finden(LIZENZKLASSEN, wert)


def zuweisungsart_anzeigename(wert):
    return anzeigename_finden(ZUWEISUNGSARTEN, wert)


def kostenmodell_anzeigename(wert):
    if wert == "monatlich":
        return "Monatlich"
    if wert == "jährlich":
        return "Jährlich"
    return anzeigename_finden(KOSTENMODELLE, wert)


def technologiebereich_anzeigename(wert):
    return anzeigename_finden(TECHNOLOGIEBEREICHE, wert)
