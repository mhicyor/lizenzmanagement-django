def _wert_aus_tuple(daten, index, standard=""):
    """
    Liest einen Wert sicher aus einem Tupel oder einer Liste.

    Dadurch bleiben ältere Datensätze und unterschiedliche
    Abfrageformate kompatibel.
    """
    if daten is None:
        return standard

    if len(daten) <= index:
        return standard

    wert = daten[index]

    if wert is None:
        return standard

    return wert


def ermittle_lizenz_ziel_typ(
    lizenz,
    lizenzklasse_index=8,
    kategorie_name_index=13,
    kategorie_slug_index=14,
):
    """
    Ermittelt, ob eine Lizenz Benutzern oder Geräten
    zugewiesen werden soll.

    Die vorhandene technische Lizenzklasse wird zuerst
    berücksichtigt. Eindeutige Kategoriebezeichnungen
    haben anschließend Vorrang.

    Server bleiben aus Kompatibilitätsgründen erhalten,
    stehen aber nicht im Mittelpunkt der aktuellen UI.
    """
    lizenzklasse = str(
        _wert_aus_tuple(
            lizenz,
            lizenzklasse_index,
            "",
        )
    ).strip().lower()

    kategorie_name = str(
        _wert_aus_tuple(
            lizenz,
            kategorie_name_index,
            "",
        )
    ).strip().lower()

    kategorie_slug = str(
        _wert_aus_tuple(
            lizenz,
            kategorie_slug_index,
            "",
        )
    ).strip().lower()

    zielbasis = " ".join([
        lizenzklasse,
        kategorie_name,
        kategorie_slug,
    ])

    geraete_begriffe = (
        "gerät",
        "geraet",
        "gerätebasiert",
        "geraetebasiert",
        "gerätelizenz",
        "geraetelizenz",
        "device",
        "endpoint",
    )

    benutzer_begriffe = (
        "benutzerbasiert",
        "nutzerbasiert",
        "benutzerlizenz",
        "nutzerlizenz",
        "named user",
        "user based",
    )

    if any(
        begriff in zielbasis
        for begriff in geraete_begriffe
    ):
        return "geraet"

    if any(
        begriff in zielbasis
        for begriff in benutzer_begriffe
    ):
        return "benutzer"

    if lizenzklasse in {
        "benutzer",
        "geraet",
        "server",
    }:
        return lizenzklasse

    return "benutzer"


def ist_manuell_verwaltete_lizenz(
    lizenz,
    datenquelle_index,
    api_sync_index,
):
    """
    Prüft, ob eine Lizenz lokal und manuell verwaltet wird.

    Manuell bedeutet:
    - Datenquelle ist leer oder 'manuell'
    - API-Synchronisation ist nicht aktiviert
    """
    datenquelle = str(
        _wert_aus_tuple(
            lizenz,
            datenquelle_index,
            "manuell",
        )
    ).strip().lower()

    api_sync_roh = _wert_aus_tuple(
        lizenz,
        api_sync_index,
        0,
    )

    try:
        api_sync_aktiv = int(api_sync_roh or 0)
    except (TypeError, ValueError):
        api_sync_aktiv = 0

    return (
        datenquelle in {
            "",
            "manuell",
        }
        and api_sync_aktiv == 0
    )


def ist_datenquellen_lizenz(
    lizenz,
    datenquelle_index,
    api_sync_index,
):
    """
    Gegenstück zu ist_manuell_verwaltete_lizenz().
    """
    return not ist_manuell_verwaltete_lizenz(
        lizenz,
        datenquelle_index,
        api_sync_index,
    )


def gespeicherte_datenquelle_laden(
    lizenz,
    datenquelle_index,
):
    """
    Gibt den gespeicherten Datenquellenwert als String zurück.

    Ergebnis:
    - 'manuell'
    - eine Datenquellen-ID wie '3'
    """
    datenquelle = str(
        _wert_aus_tuple(
            lizenz,
            datenquelle_index,
            "manuell",
        )
    ).strip()

    return datenquelle or "manuell"
